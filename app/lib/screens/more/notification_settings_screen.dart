import 'package:flutter/foundation.dart' show kIsWeb;
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../models/account.dart';
import '../../providers/providers.dart';
import '../../widgets/common.dart';
import '../../l10n/l10n.dart';
import 'ntfy_card.dart';

/// Kategorien an/aus, Ruhezeiten, registrierte Geräte, Test-Nachricht.
class NotificationSettingsScreen extends ConsumerStatefulWidget {
  const NotificationSettingsScreen({super.key});

  @override
  ConsumerState<NotificationSettingsScreen> createState() => _NotificationSettingsScreenState();
}

class _NotificationSettingsScreenState extends ConsumerState<NotificationSettingsScreen> {
  Map<String, NotificationPref>? _prefs;
  TimeOfDay? _quietStart;
  TimeOfDay? _quietEnd;
  Object? _error;
  bool _dirty = false;
  String? _vapidKey;

  @override
  void initState() {
    super.initState();
    _load();
    // Web: Schlüssel vorab laden, damit der Tipp direkt die Erlaubnis abfragen kann (iOS)
    if (kIsWeb) {
      ref.read(apiClientProvider).vapidPublicKey().then((k) {
        if (mounted) setState(() => _vapidKey = k);
      }).catchError((_) {});
    }
  }

  Future<void> _enableWebPush() async {
    final key = _vapidKey;
    if (key == null) return;
    final push = ref.read(pushServiceProvider);
    final ok = await push.enableWebPush(key);
    if (!mounted) return;
    setState(() {});
    ref.invalidate(devicesProvider);
    showInfo(context, ok ? l10n.pushEnabledHere : (push.lastError ?? l10n.notEnabled));
  }

  Future<void> _load() async {
    try {
      final saved = await ref.read(apiClientProvider).notificationPrefs();
      final byCat = {for (final p in saved) p.category: p};
      final first = saved.where((p) => p.quietStart != null).firstOrNull;
      if (!mounted) return;
      setState(() {
        _prefs = {
          for (final c in notificationCategories.keys) c: byCat[c] ?? NotificationPref(category: c),
        };
        _quietStart = _parse(first?.quietStart);
        _quietEnd = _parse(first?.quietEnd);
        _error = null;
      });
    } catch (e) {
      if (mounted) setState(() => _error = e);
    }
  }

  static TimeOfDay? _parse(String? hhmm) {
    if (hhmm == null || !hhmm.contains(':')) return null;
    final p = hhmm.split(':');
    return TimeOfDay(hour: int.parse(p[0]), minute: int.parse(p[1]));
  }

  static String _fmt(TimeOfDay t) => '${t.hour.toString().padLeft(2, '0')}:${t.minute.toString().padLeft(2, '0')}';

  Future<void> _save() async {
    final quiet = _quietStart != null && _quietEnd != null;
    final prefs = [
      for (final p in _prefs!.values)
        p.copyWith(
          quietStart: quiet ? _fmt(_quietStart!) : null,
          quietEnd: quiet ? _fmt(_quietEnd!) : null,
          clearQuiet: !quiet,
        ),
    ];
    if (await runAction(context, () => ref.read(apiClientProvider).saveNotificationPrefs(prefs))) {
      if (!mounted) return;
      setState(() => _dirty = false);
      showInfo(context, l10n.saved);
    }
  }

  Future<void> _pickQuiet(bool start) async {
    final t = await showTimePicker(
      context: context,
      initialTime: (start ? _quietStart : _quietEnd) ??
          (start ? const TimeOfDay(hour: 22, minute: 0) : const TimeOfDay(hour: 7, minute: 0)),
    );
    if (t == null) return;
    setState(() {
      if (start) {
        _quietStart = t;
      } else {
        _quietEnd = t;
      }
      _dirty = true;
    });
  }

  @override
  Widget build(BuildContext context) {
    final push = ref.watch(pushServiceProvider);
    final prefs = _prefs;
    return Scaffold(
      appBar: AppBar(
        title: Text(l10n.notificationSettings),
        actions: [
          if (_dirty) TextButton(onPressed: _save, child: Text(l10n.save)),
        ],
      ),
      body: _error != null
          ? ErrorView(error: _error!, onRetry: _load)
          : prefs == null
              ? const Center(child: HubLoader())
              : ListView(
                  children: [
                    if (kIsWeb && !push.available)
                      Padding(
                        padding: const EdgeInsets.all(16),
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.stretch,
                          children: [
                            if (push.webPushHint() != null)
                              Padding(
                                padding: const EdgeInsets.only(bottom: 8),
                                child: Text(push.webPushHint()!),
                              ),
                            FilledButton.icon(
                              key: const Key('enable-web-push'),
                              icon: const Icon(Icons.notifications_active),
                              label: Text(l10n.enablePushHere),
                              onPressed: _vapidKey == null ? null : _enableWebPush,
                            ),
                          ],
                        ),
                      )
                    else if (!push.available)
                      Padding(
                        padding: const EdgeInsets.all(16),
                        child: Text(
                          l10n.pushOffHere(push.lastError ?? l10n.firebaseNotSetUp),
                          style: TextStyle(color: Theme.of(context).colorScheme.onSurfaceVariant),
                        ),
                      ),
                    const NtfyCard(),
                    for (final entry in notificationCategories.entries)
                      SwitchListTile(
                        title: Text(entry.value),
                        value: prefs[entry.key]!.enabled,
                        onChanged: (v) => setState(() {
                          prefs[entry.key] = prefs[entry.key]!.copyWith(enabled: v);
                          _dirty = true;
                        }),
                      ),
                    const Divider(),
                    ListTile(
                      leading: const Icon(Icons.bedtime_outlined),
                      title: Text(l10n.quietHours),
                      subtitle: Text(_quietStart == null || _quietEnd == null
                          ? l10n.stateOff
                          : '${_fmt(_quietStart!)} – ${_fmt(_quietEnd!)}'),
                      trailing: _quietStart == null
                          ? null
                          : IconButton(
                              tooltip: l10n.quietHoursOff,
                              icon: const Icon(Icons.clear),
                              onPressed: () => setState(() {
                                _quietStart = null;
                                _quietEnd = null;
                                _dirty = true;
                              }),
                            ),
                    ),
                    Padding(
                      padding: const EdgeInsets.symmetric(horizontal: 16),
                      child: Row(
                        children: [
                          OutlinedButton(onPressed: () => _pickQuiet(true), child: Text(l10n.fromTime(_quietStart == null ? '–' : _fmt(_quietStart!)))),
                          const SizedBox(width: 8),
                          OutlinedButton(onPressed: () => _pickQuiet(false), child: Text(l10n.untilTime(_quietEnd == null ? '–' : _fmt(_quietEnd!)))),
                        ],
                      ),
                    ),
                    const SizedBox(height: 16),
                    const Divider(),
                    const _DevicesSection(),
                  ],
                ),
    );
  }
}

class _DevicesSection extends ConsumerWidget {
  const _DevicesSection();

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final devices = ref.watch(devicesProvider);
    final format = localDate('d.M.yyyy HH:mm');
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Padding(
          padding: const EdgeInsets.fromLTRB(16, 8, 16, 0),
          child: Text(l10n.devices, style: Theme.of(context).textTheme.titleMedium),
        ),
        devices.when(
          loading: () => const Padding(padding: EdgeInsets.all(16), child: LinearProgressIndicator()),
          error: (e, _) => Padding(padding: const EdgeInsets.all(16), child: Text(errorText(e))),
          data: (list) => Column(
            children: [
              if (list.isEmpty)
                ListTile(title: Text(l10n.noDevices)),
              for (final d in list)
                ListTile(
                  leading: Icon(d.kind == 'fcm' ? Icons.phone_android : Icons.language),
                  title: Text(d.deviceName ?? (d.kind == 'fcm' ? 'Android' : 'Browser')),
                  subtitle: d.lastSeen == null ? null : Text(l10n.lastSeen(format.format(d.lastSeen!))),
                  trailing: IconButton(
                    tooltip: l10n.remove,
                    icon: const Icon(Icons.delete_outline),
                    onPressed: () async {
                      if (await runAction(context, () => ref.read(apiClientProvider).deleteDevice(d.id))) {
                        ref.invalidate(devicesProvider);
                      }
                    },
                  ),
                ),
            ],
          ),
        ),
        Padding(
          padding: const EdgeInsets.all(16),
          child: FilledButton.tonalIcon(
            icon: const Icon(Icons.send),
            label: Text(l10n.sendTestNotification),
            onPressed: () async {
              try {
                final sent = await ref.read(apiClientProvider).testPush();
                if (!context.mounted) return;
                showInfo(
                  context,
                  sent == 0
                      ? l10n.noDeviceReached
                      : l10n.testSentCount(sent),
                );
              } catch (e) {
                if (context.mounted) showError(context, e);
              }
            },
          ),
        ),
      ],
    );
  }
}
