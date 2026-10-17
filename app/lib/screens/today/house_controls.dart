import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../models/common.dart';
import '../../models/today.dart';
import '../../providers/providers.dart';
import '../../core/theme/hub_style.dart';
import '../../widgets/common.dart';

/// Eine Haus-Karte mit Kacheln wie in Home Assistant: ausgewählte Zustände (aus „Heute“) und
/// freigegebene Geräte (Licht, Schalter, Szenen, Skripte) zusammen.
/// Steuerung nur über flüchtige Netzantworten; die Heute-Momentaufnahme erteilt keine Freigabe.
class HouseCard extends ConsumerStatefulWidget {
  final bool online;
  final SourceResult<TodayHouseState> states;
  const HouseCard({super.key, required this.online, this.states = const SourceResult(status: SourceStatus.notConfigured)});

  @override
  ConsumerState<HouseCard> createState() => _HouseCardState();
}

/// Erwarteter Zustand nach einer Aktion, bis HA ihn bestätigt oder die Frist abläuft.
class _Expectation {
  final String? state;
  final int? brightness;
  const _Expectation({this.state, this.brightness});

  bool matches(HouseControl c) {
    if (state != null && c.state != state) return false;
    if (brightness != null && brightness! > 0 && ((c.brightness ?? -999) - brightness!).abs() > 3) return false;
    return true;
  }
}

class _HouseCardState extends ConsumerState<HouseCard> with WidgetsBindingObserver {
  /// So oft liest die Karte im Vordergrund den echten Zustand nach (Änderungen von außen).
  static const pollEvery = Duration(seconds: 5);

  /// So lange zeigt eine Kachel den erwarteten Zustand, bevor sie auf den echten zurückfällt (wie HA).
  static const confirmWithin = Duration(seconds: 4);

  SourceResult<HouseControl>? _controls;
  bool _loading = false;
  final _brightness = <String, double>{}; // Regler wird gerade gezogen
  final _expect = <String, _Expectation>{};
  final _flash = <String>{}; // Szene/Skript kurz als ausgelöst zeigen
  final _timers = <Timer>[];
  String? _error;
  int _revision = 0;
  bool _foreground = true;
  Timer? _poll;
  StreamSubscription<void>? _logout;
  StreamSubscription<void>? _actionChanges;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    _logout = ref.read(apiClientProvider).loggedOut.listen((_) {
      _revision++;
      if (mounted) setState(() { _controls = null; _error = null; _expect.clear(); _brightness.clear(); });
    });
    _actionChanges = ref.read(apiClientProvider).houseActionChanges.listen((_) {
      if (mounted) setState(() {});
    });
    _poll = Timer.periodic(pollEvery, (_) => _quietRefresh());
    if (widget.online) _load();
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    _foreground = state == AppLifecycleState.resumed;
    if (_foreground) _quietRefresh(); // zurück in der App: sofort den aktuellen Stand
  }

  @override
  void didUpdateWidget(covariant HouseCard oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.online != widget.online) {
      _revision++;
      _controls = null;
      _expect.clear();
      if (widget.online) _load();
    }
  }

  void _quietRefresh() {
    if (!mounted || !widget.online || !_foreground || _loading || _brightness.isNotEmpty) return;
    if (!TickerMode.valuesOf(context).enabled) return; // Heute gerade nicht sichtbar
    _load();
  }

  void _later(Duration delay, VoidCallback run) {
    late final Timer timer;
    timer = Timer(delay, () {
      _timers.remove(timer);
      if (mounted) run();
    });
    _timers.add(timer);
  }

  /// Liest den echten Zustand. Die Kacheln bleiben dabei stehen (kein Leeren, kein Ladebalken).
  Future<void> _load() async {
    final revision = ++_revision;
    _loading = true;
    try {
      final data = await ref.read(apiClientProvider).houseControls();
      if (mounted && revision == _revision) setState(() { _merge(data); _error = null; });
    } catch (_) {
      if (mounted && revision == _revision && _controls == null) {
        setState(() => _error = 'Haussteuerung nicht verfügbar. Bitte aktualisieren.');
      }
    } finally {
      if (revision == _revision) _loading = false;
    }
  }

  void _merge(SourceResult<HouseControl> data) {
    _expect.removeWhere((id, e) {
      final c = data.items.where((c) => c.entityId == id).firstOrNull;
      return c == null || e.matches(c);
    });
    _controls = data;
  }

  void _confirm(HouseControl confirmed) {
    final current = _controls;
    if (current == null) return;
    _merge(SourceResult(
      status: current.status,
      error: current.error,
      items: [for (final c in current.items) c.entityId == confirmed.entityId ? confirmed : c],
    ));
  }

  Future<void> _act(HouseControl item, String action, {int? brightness}) async {
    final api = ref.read(apiClientProvider);
    if (!widget.online || api.houseActionPendingFor(item.entityId) || !item.actions.contains(action)) return;
    setState(() {
      _error = null;
      switch (action) {
        case 'turn_on':
          _expect[item.entityId] = const _Expectation(state: 'on');
        case 'turn_off':
          _expect[item.entityId] = const _Expectation(state: 'off');
        case 'brightness':
          _expect[item.entityId] = _Expectation(state: (brightness ?? 0) > 0 ? 'on' : 'off', brightness: brightness);
        case 'activate':
          _flash.add(item.entityId);
          _later(const Duration(milliseconds: 1200), () => setState(() => _flash.remove(item.entityId)));
      }
    });
    final expectation = _expect[item.entityId];
    if (expectation != null) {
      // Ohne Bestätigung innerhalb der Frist zeigt die Kachel wieder den echten Zustand (wie HA)
      _later(confirmWithin, () {
        if (identical(_expect[item.entityId], expectation)) setState(() => _expect.remove(item.entityId));
      });
    }
    _revision++; // ältere Lesevorgänge dürfen den erwarteten Zustand nicht überschreiben
    try {
      final confirmed = await api.houseAction(item.entityId, action, brightness: brightness);
      if (!mounted) return;
      setState(() {
        _brightness.remove(item.entityId);
        if (confirmed != null) _confirm(confirmed);
      });
      if (confirmed == null) {
        // HA hat den neuen Zustand noch nicht gemeldet: kurz danach nachlesen, sonst fällt die Kachel zurück
        for (final ms in [600, 1800, confirmWithin.inMilliseconds + 200]) {
          _later(Duration(milliseconds: ms), _quietRefreshNow);
        }
      }
    } catch (_) {
      // Unklarer Ausgang: Kachel zeigt wieder den gelesenen Zustand, der ApiClient meldet den Fehler.
      // Nie automatisch erneut senden.
      if (mounted) setState(() { _expect.remove(item.entityId); _brightness.remove(item.entityId); });
    }
  }

  void _quietRefreshNow() {
    if (mounted && widget.online && !_loading) _load();
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    _poll?.cancel();
    for (final t in _timers) {
      t.cancel();
    }
    _logout?.cancel();
    _actionChanges?.cancel();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final api = ref.read(apiClientProvider);
    final actionFailed = api.houseActionFailed;
    final controlsShown = actionFailed || _error != null ||
        (_controls != null && _controls!.status != SourceStatus.notConfigured);
    final statesShown = widget.states.status != SourceStatus.notConfigured;
    if (!controlsShown && !statesShown) return const SizedBox.shrink();
    final controls = _controls?.items ?? <HouseControl>[];
    final controlled = {for (final c in controls) c.entityId};
    final readOnly = [for (final s in widget.states.items) if (s.entity == null || !controlled.contains(s.entity)) s];
    final muted = TextStyle(color: Theme.of(context).colorScheme.onSurfaceVariant);
    final problem = actionFailed || _error != null;

    return SectionCard(
      key: const Key('today-house'),
      icon: Icons.home_outlined,
      title: 'Haus',
      // Aktualisiert sich selbst; der Knopf erscheint nur, wenn etwas schiefging
      trailing: problem
          ? IconButton(
              tooltip: 'Haus aktualisieren',
              visualDensity: VisualDensity.compact,
              onPressed: widget.online ? () { api.clearHouseActionFailure(); setState(() => _error = null); _load(); } : null,
              icon: const Icon(Icons.refresh, size: 20),
            )
          : null,
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        if (actionFailed) const Text('Aktion nicht bestätigt. Zustand aktualisieren; nicht automatisch erneut ausführen.'),
        if (_error != null) Text(_error!),
        if (_controls?.error != null) Text(_controls!.error!, style: muted),
        if (statesShown && !widget.states.isOk) Text('Haus-Zustände gerade nicht verfügbar', style: muted),
        LayoutBuilder(builder: (context, box) {
          const gap = 10.0;
          final cols = box.maxWidth >= 560 ? 3 : 2;
          final w = (box.maxWidth - gap * (cols - 1)) / cols;
          return Wrap(spacing: gap, runSpacing: gap, children: [
            for (final c in controls)
              SizedBox(width: w, child: _controlTile(c, widget.online && !api.houseActionPendingFor(c.entityId))),
            for (final s in readOnly)
              SizedBox(width: w, child: HouseTile(
                key: ValueKey('house-${s.entity ?? s.name}'),
                icon: houseIcon(s.entity, s.name, s.unit, s.state),
                name: s.name,
                value: s.displayValue,
                active: s.state == 'on',
              )),
          ]);
        }),
      ]),
    );
  }

  Widget _controlTile(HouseControl c, bool enabled) {
    final domain = c.entityId.split('.').first;
    final expected = _expect[c.entityId];
    // Angezeigt wird der erwartete Zustand, geschaltet wird ausgehend davon (wie in HA)
    final state = expected?.state ?? c.state;
    final on = state == 'on' || _flash.contains(c.entityId);
    final next = c.actions.contains('activate')
        ? 'activate'
        : state == 'on' && c.actions.contains('turn_off')
            ? 'turn_off'
            : state != 'on' && c.actions.contains('turn_on')
                ? 'turn_on'
                : null;
    // Schlüssel nach bestätigtem Zustand: bleibt stabil, solange HA noch nicht geantwortet hat
    final confirmedNext = c.actions.contains('activate')
        ? 'activate'
        : c.state == 'on' && c.actions.contains('turn_off')
            ? 'turn_off'
            : c.state != 'on' && c.actions.contains('turn_on')
                ? 'turn_on'
                : null;
    final dimmable = c.actions.contains('brightness');
    final level = _brightness[c.entityId] ?? (expected?.brightness ?? c.brightness ?? 0).toDouble();
    final percent = (level / 255 * 100).round();
    final shownValue = state == null ? c.displayValue : (state == 'on' ? 'An' : state == 'off' ? 'Aus' : c.displayValue);
    final value = switch (domain) {
      'scene' => 'Szene',
      'script' => 'Skript',
      _ => dimmable && state == 'on' ? '$shownValue · $percent %' : shownValue,
    };
    return HouseTile(
      key: Key(confirmedNext == null ? '${c.entityId}-tile' : '${c.entityId}-$confirmedNext'),
      icon: houseIcon(c.entityId, c.name, null, state),
      name: c.name,
      value: value,
      active: on,
      onTap: next != null && enabled ? () => _act(c, next) : null,
      slider: dimmable
          ? Slider(
              key: Key('${c.entityId}-brightness'),
              label: 'Helligkeit',
              min: 0, max: 255, divisions: 255,
              value: level,
              semanticFormatterCallback: (v) => '${c.name}: Helligkeit ${v.round()} von 255',
              onChanged: enabled ? (v) => setState(() => _brightness[c.entityId] = v) : null,
              onChangeEnd: enabled ? (v) => _act(c, 'brightness', brightness: v.round()) : null,
            )
          : null,
    );
  }
}

/// Symbol nach Gerätetyp, Einheit und Name (wie die Standard-Symbole in Home Assistant).
IconData houseIcon(String? entity, String name, String? unit, String? state) {
  final domain = (entity ?? '').split('.').first;
  final n = name.toLowerCase();
  final on = state == 'on';
  if (domain == 'light') return on ? Icons.lightbulb : Icons.lightbulb_outline;
  if (domain == 'switch') return Icons.power_settings_new;
  if (domain == 'scene') return Icons.palette_outlined;
  if (domain == 'script') return Icons.play_circle_outline;
  if (n.contains('wasch') || n.contains('trockner')) return Icons.local_laundry_service_outlined;
  if (n.contains('baby')) return Icons.child_care;
  if (n.contains('müll') || n.contains('abfall') || n.contains('tonne')) return Icons.delete_outline;
  if (n.contains('tür') || n.contains('door')) return on ? Icons.door_front_door : Icons.door_front_door_outlined;
  if (n.contains('fenster') || n.contains('window')) return Icons.window_outlined;
  if (unit == '°C' || unit == '°F' || n.contains('temperatur')) return Icons.thermostat;
  if (unit == '%' && (n.contains('feucht') || n.contains('humid'))) return Icons.water_drop_outlined;
  if (unit == '%' && (n.contains('akku') || n.contains('batter'))) return Icons.battery_std;
  if (unit == 'W' || unit == 'kW' || unit == 'kWh') return Icons.bolt;
  return domain == 'binary_sensor' ? Icons.sensors : Icons.info_outline;
}

const _tileAnimation = Duration(milliseconds: 220);

/// Kachel wie in Home Assistant: Symbol in einem Kreis, Name, Zustand; aktiv eingefärbt. Stil kommt vom Theme.
class HouseTile extends StatelessWidget {
  final IconData icon;
  final String name;
  final String value;
  final bool active;
  final VoidCallback? onTap;
  final Widget? slider;
  const HouseTile({super.key, required this.icon, required this.name, required this.value,
    this.active = false, this.onTap, this.slider});

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final style = HubStyle.of(context);
    final accent = style.bandHeader && style.accents.isNotEmpty ? style.accents.first : theme.colorScheme.primary;
    final heavy = style.borderWidth >= 2;
    final radius = BorderRadius.circular((style.radius * 0.7).clamp(10.0, 24.0));
    final fill = active
        ? accent.withValues(alpha: style.glass ? 0.28 : 0.16)
        : theme.colorScheme.onSurface.withValues(alpha: style.glass ? 0.07 : 0.045);
    final onAccent = ThemeData.estimateBrightnessForColor(accent) == Brightness.dark ? Colors.white : Colors.black;
    return AnimatedContainer(
      duration: _tileAnimation,
      curve: Curves.easeOutCubic,
      decoration: ShapeDecoration(
        color: fill,
        shape: RoundedRectangleBorder(
          borderRadius: radius,
          side: heavy ? BorderSide(color: style.border, width: 2) : BorderSide.none,
        ),
      ),
      child: Material(
      type: MaterialType.transparency,
      shape: RoundedRectangleBorder(borderRadius: radius),
      clipBehavior: Clip.antiAlias,
      child: InkWell(
        onTap: onTap,
        child: Padding(
          padding: const EdgeInsets.fromLTRB(10, 10, 10, 8),
          child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            Row(children: [
              AnimatedContainer(
                duration: _tileAnimation,
                curve: Curves.easeOutCubic,
                width: 36, height: 36,
                decoration: BoxDecoration(
                  shape: BoxShape.circle,
                  color: active ? accent : theme.colorScheme.onSurface.withValues(alpha: 0.08),
                  border: heavy ? Border.all(color: style.border, width: 2) : null,
                ),
                child: AnimatedSwitcher(
                  duration: _tileAnimation,
                  child: Icon(icon, key: ValueKey('$icon-$active'), size: 20,
                      color: active ? onAccent : theme.colorScheme.onSurfaceVariant),
                ),
              ),
              const SizedBox(width: 10),
              Expanded(child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                Text(name, maxLines: 1, overflow: TextOverflow.ellipsis,
                    style: theme.textTheme.bodyMedium?.copyWith(fontWeight: FontWeight.w600)),
                Text(value, maxLines: 1, overflow: TextOverflow.ellipsis,
                    style: theme.textTheme.bodySmall?.copyWith(color: theme.colorScheme.onSurfaceVariant)),
              ])),
            ]),
            if (slider != null)
              SliderTheme(
                data: SliderTheme.of(context).copyWith(
                  trackHeight: 6,
                  activeTrackColor: accent,
                  thumbColor: accent,
                  overlayShape: SliderComponentShape.noOverlay,
                ),
                child: SizedBox(height: 28, child: slider!),
              ),
          ]),
        ),
      ),
      ),
    );
  }
}
