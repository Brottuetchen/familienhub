import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../models/admin.dart';
import '../../providers/providers.dart';
import '../../widgets/common.dart';
import '../today/house_controls.dart' show houseIcon;
import '../../l10n/l10n.dart';

/// Haus: Geräte aus Home Assistant für die Haus-Karte auswählen, statt Entitäts-IDs zu tippen.
/// Je Gerät: aus · anzeigen · schalten (nur Licht, Schalter, Szene, Skript). Je höchstens 6.
class AdminHouseScreen extends ConsumerStatefulWidget {
  const AdminHouseScreen({super.key});

  @override
  ConsumerState<AdminHouseScreen> createState() => _AdminHouseScreenState();
}

enum _Mode { off, show, control }

class _AdminHouseScreenState extends ConsumerState<AdminHouseScreen> {
  HouseChoices? _choices;
  Object? _error;
  final _display = <String>[];
  final _control = <String>[];
  final _query = TextEditingController();
  bool _dirty = false;
  bool _saving = false;

  @override
  void initState() {
    super.initState();
    _load();
  }

  @override
  void dispose() {
    _query.dispose();
    super.dispose();
  }

  Future<void> _load() async {
    try {
      final c = await ref.read(apiClientProvider).houseChoices();
      if (!mounted) return;
      setState(() {
        _choices = c;
        _error = null;
        _display..clear()..addAll(c.display);
        _control..clear()..addAll(c.control);
        _dirty = false;
      });
    } catch (e) {
      if (mounted) setState(() => _error = e);
    }
  }

  _Mode _modeOf(String id) => _control.contains(id) ? _Mode.control : _display.contains(id) ? _Mode.show : _Mode.off;

  void _set(HaEntity e, _Mode mode) {
    final max = _choices?.max ?? 6;
    if (mode == _Mode.show && !_display.contains(e.entityId) && _display.length >= max ||
        mode == _Mode.control && !_control.contains(e.entityId) && _control.length >= max) {
      showInfo(context, l10n.maxDevices(max));
      return;
    }
    setState(() {
      _display.remove(e.entityId);
      _control.remove(e.entityId);
      if (mode == _Mode.show) _display.add(e.entityId);
      if (mode == _Mode.control) _control.add(e.entityId);
      _dirty = true;
    });
  }

  Future<void> _save() async {
    setState(() => _saving = true);
    final ok = await runAction(
        context, () => ref.read(apiClientProvider).saveHouseSelection(display: _display, control: _control));
    if (!mounted) return;
    setState(() {
      _saving = false;
      if (ok) _dirty = false;
    });
    if (ok) {
      showInfo(context, l10n.houseCardSaved);
      ref.read(todayProvider.notifier).refresh().ignore();
    }
  }

  @override
  Widget build(BuildContext context) {
    final c = _choices;
    return Scaffold(
      appBar: AppBar(
        title: Text(l10n.house),
        actions: [
          TextButton(
            key: const Key('admin-house-save'),
            onPressed: _dirty && !_saving ? _save : null,
            child: Text(l10n.save),
          ),
        ],
      ),
      body: _error != null
          ? ErrorView(error: _error!, onRetry: _load)
          : c == null
              ? const Center(child: HubLoader())
              : c.status != 'ok'
                  ? EmptyHint(
                      icon: Icons.home_outlined,
                      text: c.status == 'not_configured'
                          ? l10n.haNotSetUp
                          : l10n.haUnavailable)
                  : _body(c),
    );
  }

  Widget _body(HouseChoices c) {
    final theme = Theme.of(context);
    final byId = {for (final e in c.items) e.entityId: e};
    final q = _query.text.trim().toLowerCase();
    final shown = q.isEmpty
        ? c.items
        : c.items.where((e) => e.name.toLowerCase().contains(q) || e.entityId.contains(q)).toList();

    Widget selected(String title, List<String> ids) => Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Padding(
            padding: const EdgeInsets.fromLTRB(16, 12, 16, 4),
            child: Text('$title (${ids.length}/${c.max})',
                style: theme.textTheme.titleSmall?.copyWith(color: theme.colorScheme.primary)),
          ),
          if (ids.isEmpty)
            Padding(padding: const EdgeInsets.fromLTRB(16, 0, 16, 8), child: Text(l10n.nothingSelected, style: theme.textTheme.bodySmall)),
          ReorderableListView(
            shrinkWrap: true,
            physics: const NeverScrollableScrollPhysics(),
            buildDefaultDragHandles: true,
            onReorderItem: (from, to) => setState(() {
              ids.insert(to, ids.removeAt(from)); // „to“ ist schon um das entfernte Element bereinigt
              _dirty = true;
            }),
            children: [
              for (final id in ids)
                ListTile(
                  key: ValueKey('sel-$title-$id'),
                  dense: true,
                  leading: Icon(houseIcon(id, byId[id]?.name ?? id, byId[id]?.unit, byId[id]?.state)),
                  title: Text(byId[id]?.name ?? id),
                  subtitle: byId[id] == null ? Text(l10n.notInHa) : null,
                ),
            ],
          ),
        ]);

    return ListView(padding: const EdgeInsets.only(bottom: 32), children: [
      Padding(
        padding: EdgeInsets.fromLTRB(16, 12, 16, 0),
        child: Text(l10n.houseAdminExplain),
      ),
      selected(l10n.control, _control),
      selected(l10n.show, _display),
      const Divider(height: 24),
      Padding(
        padding: const EdgeInsets.symmetric(horizontal: 16),
        child: TextField(
          key: const Key('admin-house-search'),
          controller: _query,
          onChanged: (_) => setState(() {}), // lokal gefiltert, keine Anfrage
          decoration: InputDecoration(prefixIcon: Icon(Icons.search), hintText: l10n.searchDevice),
        ),
      ),
      for (final e in shown.take(200))
        ListTile(
          key: ValueKey('ha-${e.entityId}'),
          leading: Icon(houseIcon(e.entityId, e.name, e.unit, e.state)),
          title: Text(e.name, maxLines: 1, overflow: TextOverflow.ellipsis),
          subtitle: Text('${e.entityId} · ${e.stateLabel}', maxLines: 1, overflow: TextOverflow.ellipsis),
          trailing: SegmentedButton<_Mode>(
            key: ValueKey('ha-mode-${e.entityId}'),
            showSelectedIcon: false,
            style: const ButtonStyle(visualDensity: VisualDensity.compact),
            segments: [
              ButtonSegment(value: _Mode.off, icon: Icon(Icons.close, size: 16), tooltip: l10n.notOnCard),
              ButtonSegment(value: _Mode.show, icon: Icon(Icons.visibility_outlined, size: 16), tooltip: l10n.show),
              if (e.controllable)
                ButtonSegment(value: _Mode.control, icon: Icon(Icons.touch_app_outlined, size: 16), tooltip: l10n.control),
            ],
            selected: {_modeOf(e.entityId)},
            onSelectionChanged: (s) => _set(e, s.first),
          ),
        ),
      if (shown.length > 200)
        Padding(padding: EdgeInsets.all(16), child: Text(l10n.moreHits)),
    ]);
  }
}
