import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../l10n/l10n.dart';
import '../../models/plugin_card.dart';
import '../../models/stars.dart';
import '../../providers/providers.dart';
import '../../services/api_client.dart';
import '../../widgets/common.dart';

/// Kids mode: stars, rewards and requests. Children see their balance and ask for rewards; parents decide on
/// requests and confirmations, manage rewards and see every child's balance. The server enforces all roles.
class StarsScreen extends ConsumerStatefulWidget {
  const StarsScreen({super.key});

  @override
  ConsumerState<StarsScreen> createState() => _StarsScreenState();
}

class _StarsScreenState extends ConsumerState<StarsScreen> {
  Future<StarsOverview>? _load;
  bool _parent = false;

  Future<StarsOverview> _fetch() => ref.read(apiClientProvider).starsOverview(parent: _parent);

  Future<void> _reload() async {
    final next = _fetch();
    setState(() {
      _load = next;
    });
    await next.then<void>((_) {}, onError: (_) {});
  }

  /// Runs a change, then reloads this screen. The Today card refreshes through the cache invalidation.
  Future<void> _do(Future<void> Function() action, {String? done}) async {
    final ok = await runAction(context, action);
    if (!mounted) return;
    if (ok && done != null) showInfo(context, done);
    await _reload();
  }

  @override
  Widget build(BuildContext context) {
    final api = ref.watch(apiClientProvider);
    // The role decides which endpoints are read; wait until the session knows who this is
    final user = ref.watch(sessionProvider).user;
    if (user != null && _load == null) {
      _parent = user.roleLevel >= 2;
      _load = _fetch();
    }
    return Scaffold(
      appBar: AppBar(title: Text(l10n.starsTitle)),
      body: HubRefresh(
        onRefresh: _reload,
        child: FutureBuilder<StarsOverview>(
          future: _load,
          builder: (context, snap) {
            if (_load == null || snap.connectionState != ConnectionState.done) return const Center(child: HubLoader());
            if (snap.hasError) return ErrorView(error: snap.error!, onRetry: _reload);
            final o = snap.data!;
            return ListView(
              key: const Key('stars-list'),
              physics: const AlwaysScrollableScrollPhysics(),
              padding: const EdgeInsets.only(bottom: 32),
              children: _parent ? _parentSections(o, api) : _childSections(o, api),
            );
          },
        ),
      ),
    );
  }

  // ── child ──────────────────────────────────────────────────────────────────

  List<Widget> _childSections(StarsOverview o, ApiClient api) {
    return [
      StarsBalance(summary: o.me),
      _Header(l10n.rewards),
      if (o.rewards.isEmpty) _Muted(l10n.starsNoRewards),
      for (final r in o.rewards)
        ListTile(
          key: Key('reward-${r.id}'),
          title: Text(r.title),
          subtitle: Text(l10n.starsCount(r.price)),
          trailing: FilledButton(
            key: Key('reward-request-${r.id}'),
            onPressed: r.price > o.me.available
                ? null
                : () => _do(() => api.requestReward(r.id), done: l10n.rewardRequested),
            child: Text(l10n.rewardRequest),
          ),
        ),
      if (o.requests.any((r) => r.status == 'pending')) ...[
        _Header(l10n.rewardStatusPending),
        for (final r in o.requests.where((r) => r.status == 'pending'))
          ListTile(
            key: Key('request-${r.id}'),
            title: Text(r.title),
            subtitle: Text(l10n.starsCount(r.price)),
            trailing: TextButton(
              onPressed: () => _do(() => api.cancelRewardRequest(r.id)),
              child: Text(l10n.rewardWithdraw),
            ),
          ),
      ],
      _Header(l10n.starsHistory),
      if (o.history.isEmpty) _Muted(l10n.starsNoHistory),
      for (final e in o.history.take(30)) _EntryTile(entry: e),
    ];
  }

  // ── parent ─────────────────────────────────────────────────────────────────

  List<Widget> _parentSections(StarsOverview o, ApiClient api) {
    return [
      if (o.requests.isNotEmpty || o.awards.isNotEmpty) ...[
        _Header(l10n.starsToDecide),
        for (final r in o.requests)
          _DecisionTile(
            key: Key('decide-request-${r.id}'),
            title: r.title,
            subtitle: '${r.userName} · ${l10n.starsCount(r.price)}',
            primary: l10n.starsApprove,
            secondary: l10n.starsDecline,
            onPrimary: () => _approve(r.id),
            onSecondary: () => _do(() => api.decideRewardRequest(r.id, approve: false)),
          ),
        for (final a in o.awards)
          _DecisionTile(
            key: Key('decide-award-${a.id}'),
            title: a.title.isEmpty ? l10n.task : a.title,
            subtitle: '${a.userName} · +${l10n.starsCount(a.delta)}',
            primary: l10n.starsConfirm,
            secondary: l10n.starsDecline,
            onPrimary: () => _do(() => api.decideStarEntry(a.id, confirm: true)),
            onSecondary: () => _do(() => api.decideStarEntry(a.id, confirm: false)),
          ),
      ],
      _Header(l10n.starsChildren),
      for (final p in o.people)
        ListTile(
          key: Key('person-${p.id}'),
          title: Text(p.name),
          subtitle: Text(l10n.starsAvailable(p.available)),
          trailing: const Icon(Icons.chevron_right),
          onTap: () => _openPerson(p),
        ),
      _Header(l10n.rewards),
      if (o.rewards.isEmpty) _Muted(l10n.starsNoRewards),
      for (final r in o.rewards)
        ListTile(
          key: Key('reward-${r.id}'),
          title: Text(r.title, style: r.active ? null : TextStyle(color: Theme.of(context).disabledColor)),
          subtitle: Text(r.active ? l10n.starsCount(r.price) : '${l10n.starsCount(r.price)} · ${l10n.rewardHidden}'),
          onTap: () => _editReward(r),
          trailing: IconButton(
            tooltip: r.active ? l10n.rewardHide : l10n.rewardShow,
            icon: Icon(r.active ? Icons.visibility_off_outlined : Icons.visibility_outlined),
            onPressed: () => _do(() => api.setRewardActive(r.id, !r.active)),
          ),
        ),
      Padding(
        padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
        child: Align(
          alignment: Alignment.centerLeft,
          child: OutlinedButton.icon(
            key: const Key('reward-add'),
            onPressed: () => _editReward(null),
            icon: const Icon(Icons.add),
            label: Text(l10n.addReward),
          ),
        ),
      ),
      const Divider(),
      SwitchListTile(
        key: const Key('stars-confirm-tasks'),
        title: Text(l10n.starsConfirmTasks),
        subtitle: Text(l10n.starsConfirmTasksHint),
        value: o.confirmTasks,
        onChanged: (v) => _do(() => api.setConfirmTasks(v)),
      ),
    ];
  }

  /// Approving can run the reward's plugin action; its outcome is shown, a failure never undoes the approval.
  Future<void> _approve(int id) async {
    RewardActionResult? outcome;
    final ok = await runAction(context, () async {
      outcome = await ref.read(apiClientProvider).decideRewardRequest(id, approve: true);
    });
    if (!mounted) return;
    final r = outcome;
    if (ok && r != null) showInfo(context, r.ok ? l10n.rewardActionDone(r.message) : l10n.rewardActionFailed(r.message));
    await _reload();
  }

  Future<void> _editReward(StarReward? reward) async {
    final api = ref.read(apiClientProvider);
    // Actions come from plugins; without any (or when they cannot be read) the form simply has no such field
    final choices = api.rewardActionChoices().catchError((Object _) => const <RewardActionChoice>[]);
    final result = await showDialog<_RewardEdit>(
      context: context,
      builder: (_) => _RewardDialog(reward: reward, choices: choices),
    );
    if (result == null || !mounted) return;
    await _do(() => api.saveReward(
        id: reward?.id,
        title: result.title,
        price: result.price,
        action: result.action,
        setAction: result.actionChanged));
  }

  Future<void> _openPerson(StarPerson p) async {
    await showModalBottomSheet<void>(
      context: context,
      isScrollControlled: true,
      showDragHandle: true,
      builder: (_) => _PersonSheet(person: p, onChanged: _reload),
    );
  }
}

/// What the reward dialog returns: the new values, and the plugin action if the parent changed it.
typedef _RewardEdit = ({String title, int price, RewardActionRef? action, bool actionChanged});

/// Add or edit a reward. Owns its text controllers, so they live as long as the dialog animates.
/// [choices] are the actions of active plugins; with none (and none set) the form has no action field.
class _RewardDialog extends StatefulWidget {
  final StarReward? reward;
  final Future<List<RewardActionChoice>> choices;
  const _RewardDialog({this.reward, required this.choices});

  @override
  State<_RewardDialog> createState() => _RewardDialogState();
}

class _RewardDialogState extends State<_RewardDialog> {
  late final _title = TextEditingController(text: widget.reward?.title ?? '');
  late final _price = TextEditingController(text: widget.reward == null ? '' : '${widget.reward!.price}');
  final Map<String, TextEditingController> _params = {};
  final Map<String, String> _picked = {}; // select and switch values by parameter key
  List<RewardActionChoice> _choices = const [];
  String? _selected; // "plugin/action" or null (no action)
  bool _touched = false; // the parent changed the action or one of its values
  String? _paramError;

  RewardActionRef? get _current => widget.reward?.action;

  static String _id(String plugin, String action) => '$plugin/$action';

  RewardActionChoice? get _choice => _choices.where((c) => _id(c.plugin, c.id) == _selected).firstOrNull;

  @override
  void initState() {
    super.initState();
    final current = _current;
    if (current != null) _selected = _id(current.plugin, current.action);
    widget.choices.then((list) {
      if (!mounted) return;
      setState(() {
        _choices = list;
        _prepare(preset: current?.params ?? const {});
      });
    });
  }

  void _prepare({Map<String, String> preset = const {}}) {
    for (final c in _params.values) {
      c.dispose();
    }
    _params.clear();
    _picked.clear();
    for (final p in _choice?.params ?? const <RewardActionParam>[]) {
      final start = preset[p.key] ?? p.defaultValue ?? (p.type == 'bool' ? 'false' : '');
      if (p.type == 'text' || p.type == 'number') {
        _params[p.key] = TextEditingController(text: start);
      } else {
        _picked[p.key] = start.isEmpty && p.options.isNotEmpty ? p.options.first.$1 : start;
      }
    }
  }

  @override
  void dispose() {
    _title.dispose();
    _price.dispose();
    for (final c in _params.values) {
      c.dispose();
    }
    super.dispose();
  }

  void _save() {
    final price = int.tryParse(_price.text.trim());
    final title = _title.text.trim();
    if (price == null || price < 1 || title.isEmpty) return;
    RewardActionRef? action;
    final choice = _choice;
    if (choice != null) {
      final values = <String, String>{};
      for (final p in choice.params) {
        final v = (_params[p.key]?.text ?? _picked[p.key] ?? '').trim();
        if (v.isEmpty && p.required && p.type != 'bool') {
          setState(() => _paramError = l10n.rewardActionParamMissing(p.label));
          return;
        }
        if (p.type == 'number' && v.isNotEmpty && double.tryParse(v) == null) {
          setState(() => _paramError = l10n.rewardActionParamNumber(p.label));
          return;
        }
        if (v.isNotEmpty) values[p.key] = v;
      }
      action = RewardActionRef(plugin: choice.plugin, action: choice.id, params: values);
    }
    // An action whose plugin is off is kept as long as the parent leaves it alone
    final keepUnavailable = _selected != null && choice == null && _current != null;
    Navigator.pop(context, (
      title: title,
      price: price,
      action: keepUnavailable ? null : action,
      actionChanged: _touched && !keepUnavailable,
    ));
  }

  Widget _paramField(RewardActionParam p) {
    switch (p.type) {
      case 'bool':
        return SwitchListTile(
          key: Key('reward-param-${p.key}'),
          contentPadding: EdgeInsets.zero,
          title: Text(p.label),
          subtitle: p.help.isEmpty ? null : Text(p.help),
          value: _picked[p.key] == 'true',
          onChanged: (v) => setState(() {
            _picked[p.key] = v ? 'true' : 'false';
            _touched = true;
          }),
        );
      case 'select':
        return DropdownButtonFormField<String>(
          key: Key('reward-param-${p.key}'),
          isExpanded: true,
          initialValue: p.options.any((o) => o.$1 == _picked[p.key]) ? _picked[p.key] : null,
          decoration: InputDecoration(labelText: p.required ? '${p.label} *' : p.label, helperText: p.help.isEmpty ? null : p.help),
          items: [for (final o in p.options) DropdownMenuItem(value: o.$1, child: Text(o.$2, overflow: TextOverflow.ellipsis))],
          onChanged: (v) => setState(() {
            _picked[p.key] = v ?? '';
            _touched = true;
          }),
        );
      default:
        return TextField(
          key: Key('reward-param-${p.key}'),
          controller: _params[p.key],
          keyboardType: p.type == 'number'
              ? const TextInputType.numberWithOptions(decimal: true)
              : TextInputType.text,
          decoration: InputDecoration(labelText: p.required ? '${p.label} *' : p.label, helperText: p.help.isEmpty ? null : p.help),
          onChanged: (_) => _touched = true,
        );
    }
  }

  List<Widget> _actionSection() {
    final current = _current;
    final unavailable = current != null && _selected == _id(current.plugin, current.action) && _choice == null;
    if (_choices.isEmpty && current == null) return const [];
    return [
      const SizedBox(height: 16),
      DropdownButtonFormField<String?>(
        key: const Key('reward-action'),
        isExpanded: true,
        initialValue: _selected,
        decoration: InputDecoration(labelText: l10n.rewardAction, helperText: l10n.rewardActionHint, helperMaxLines: 3),
        items: [
          DropdownMenuItem<String?>(value: null, child: Text(l10n.rewardActionNone)),
          if (current != null && _choice == null)
            DropdownMenuItem<String?>(
                value: _id(current.plugin, current.action),
                child: Text('${current.label.isEmpty ? current.action : current.label} (${l10n.rewardActionUnavailable})',
                    overflow: TextOverflow.ellipsis)),
          for (final c in _choices)
            DropdownMenuItem<String?>(
                value: _id(c.plugin, c.id), child: Text('${c.label} · ${c.pluginName}', overflow: TextOverflow.ellipsis)),
        ],
        onChanged: (v) => setState(() {
          _selected = v;
          _touched = true;
          _paramError = null;
          _prepare(preset: v == null || current == null || _id(current.plugin, current.action) != v ? const {} : current.params);
        }),
      ),
      if (unavailable)
        Padding(padding: const EdgeInsets.only(top: 8), child: Text(l10n.rewardActionPluginOff, key: const Key('reward-action-off'))),
      for (final p in _choice?.params ?? const <RewardActionParam>[])
        Padding(padding: const EdgeInsets.only(top: 8), child: _paramField(p)),
      if (_paramError != null)
        Padding(
          padding: const EdgeInsets.only(top: 8),
          child: Text(_paramError!, key: const Key('reward-action-error'), style: TextStyle(color: Theme.of(context).colorScheme.error)),
        ),
    ];
  }

  @override
  Widget build(BuildContext context) => AlertDialog(
        title: Text(widget.reward == null ? l10n.addReward : l10n.rewardTitle),
        content: SingleChildScrollView(
          child: Column(mainAxisSize: MainAxisSize.min, crossAxisAlignment: CrossAxisAlignment.stretch, children: [
            TextField(key: const Key('reward-title'), controller: _title, decoration: InputDecoration(labelText: l10n.rewardTitle)),
            const SizedBox(height: 12),
            TextField(
              key: const Key('reward-price'),
              controller: _price,
              keyboardType: TextInputType.number,
              decoration: InputDecoration(labelText: l10n.rewardPrice),
            ),
            ..._actionSection(),
          ]),
        ),
        actions: [
          TextButton(onPressed: () => Navigator.pop(context), child: Text(l10n.cancel)),
          FilledButton(key: const Key('reward-save'), onPressed: _save, child: Text(l10n.save)),
        ],
      );
}

/// Balance block: big number, reserved part, next reward with progress.
class StarsBalance extends StatelessWidget {
  final StarsSummary summary;
  const StarsBalance({super.key, required this.summary});

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final next = summary.nextReward;
    return Padding(
      padding: const EdgeInsets.all(16),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Wrap(crossAxisAlignment: WrapCrossAlignment.center, spacing: 8, children: [
          const Icon(Icons.star_rounded, color: Colors.amber, size: 36),
          Text('${summary.balance}', key: const Key('stars-balance'), style: theme.textTheme.displaySmall),
          Text(l10n.starsTitle, style: theme.textTheme.titleMedium),
        ]),
        if (summary.reserved > 0)
          Text(l10n.starsReserved(summary.reserved),
              style: theme.textTheme.bodySmall?.copyWith(color: theme.colorScheme.onSurfaceVariant)),
        if (next != null) ...[
          const SizedBox(height: 12),
          Text(l10n.nextReward, style: theme.textTheme.labelLarge),
          Text('${next.title} · ${l10n.starsCount(next.price)}'),
          const SizedBox(height: 6),
          LinearProgressIndicator(value: next.price <= 0 ? 1 : (summary.available / next.price).clamp(0.0, 1.0)),
          const SizedBox(height: 4),
          Text(next.missing > 0 ? l10n.starsMissing(next.missing) : l10n.rewardWithinReach,
              style: theme.textTheme.bodySmall?.copyWith(color: theme.colorScheme.onSurfaceVariant)),
        ],
      ]),
    );
  }
}

/// Compact content of the Today card: balance, next reward and (parents) what waits for a decision.
class StarsTile extends StatelessWidget {
  final StarsSummary summary;
  const StarsTile({super.key, required this.summary});

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final muted = theme.textTheme.bodySmall?.copyWith(color: theme.colorScheme.onSurfaceVariant);
    final next = summary.nextReward;
    return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      Wrap(crossAxisAlignment: WrapCrossAlignment.center, spacing: 6, children: [
        const Icon(Icons.star_rounded, color: Colors.amber),
        Text('${summary.balance}', key: const Key('today-stars-balance'), style: theme.textTheme.headlineSmall),
        Text(l10n.starsTitle),
      ]),
      if (next != null) ...[
        const SizedBox(height: 6),
        Text('${l10n.nextReward}: ${next.title}', maxLines: 2, overflow: TextOverflow.ellipsis),
        const SizedBox(height: 4),
        LinearProgressIndicator(value: next.price <= 0 ? 1 : (summary.available / next.price).clamp(0.0, 1.0)),
        const SizedBox(height: 2),
        Text(next.missing > 0 ? l10n.starsMissing(next.missing) : l10n.rewardWithinReach, style: muted),
      ],
      if (summary.pending > 0) ...[
        const SizedBox(height: 6),
        Text(l10n.starsWaitingForYou(summary.pending), key: const Key('today-stars-pending'), style: muted),
      ],
    ]);
  }
}

class _Header extends StatelessWidget {
  final String text;
  const _Header(this.text);

  @override
  Widget build(BuildContext context) => Padding(
        padding: const EdgeInsets.fromLTRB(16, 20, 16, 4),
        child: Text(text,
            style: Theme.of(context).textTheme.labelLarge?.copyWith(color: Theme.of(context).colorScheme.primary)),
      );
}

class _Muted extends StatelessWidget {
  final String text;
  const _Muted(this.text);

  @override
  Widget build(BuildContext context) => Padding(
        padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
        child: Text(text, style: TextStyle(color: Theme.of(context).colorScheme.onSurfaceVariant)),
      );
}

String _statusText(StarEntry e) => switch (e.status) {
      'pending' => l10n.starsAwaiting,
      'rejected' => l10n.starsRejected,
      _ => '',
    };

class _EntryTile extends StatelessWidget {
  final StarEntry entry;
  const _EntryTile({required this.entry});

  @override
  Widget build(BuildContext context) {
    final e = entry;
    final status = _statusText(e);
    final counts = e.status == 'confirmed';
    return ListTile(
      leading: Icon(e.kind == 'reward' ? Icons.card_giftcard : Icons.star_outline_rounded),
      title: Text(e.title.isEmpty ? (e.kind == 'adjust' ? l10n.starsBonus : l10n.task) : e.title),
      subtitle: status.isEmpty ? null : Text(status),
      trailing: Text(
        '${e.delta > 0 ? '+' : ''}${e.delta}',
        style: TextStyle(
          fontWeight: FontWeight.bold,
          color: counts ? null : Theme.of(context).disabledColor,
          decoration: e.status == 'rejected' ? TextDecoration.lineThrough : null,
        ),
      ),
    );
  }
}

/// Request or confirmation waiting for a parent. Buttons sit below the text, so any text size fits.
class _DecisionTile extends StatelessWidget {
  final String title, subtitle, primary, secondary;
  final VoidCallback onPrimary, onSecondary;
  const _DecisionTile({
    super.key,
    required this.title,
    required this.subtitle,
    required this.primary,
    required this.secondary,
    required this.onPrimary,
    required this.onSecondary,
  });

  @override
  Widget build(BuildContext context) => Padding(
        padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 6),
        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Text(title, style: Theme.of(context).textTheme.titleMedium),
          Text(subtitle),
          const SizedBox(height: 6),
          Wrap(spacing: 8, runSpacing: 4, children: [
            FilledButton(onPressed: onPrimary, child: Text(primary)),
            OutlinedButton(onPressed: onSecondary, child: Text(secondary)),
          ]),
        ]),
      );
}

/// History of one child plus a bonus or deduction.
class _PersonSheet extends ConsumerStatefulWidget {
  final StarPerson person;
  final Future<void> Function() onChanged;
  const _PersonSheet({required this.person, required this.onChanged});

  @override
  ConsumerState<_PersonSheet> createState() => _PersonSheetState();
}

class _PersonSheetState extends ConsumerState<_PersonSheet> {
  late Future<List<StarEntry>> _history;
  final _amount = TextEditingController();
  final _reason = TextEditingController();

  @override
  void initState() {
    super.initState();
    _history = ref.read(apiClientProvider).starsHistory(widget.person.id);
  }

  @override
  void dispose() {
    _amount.dispose();
    _reason.dispose();
    super.dispose();
  }

  Future<void> _adjust() async {
    final delta = int.tryParse(_amount.text.trim());
    if (delta == null || delta == 0) return;
    final api = ref.read(apiClientProvider);
    final ok = await runAction(context, () => api.adjustStars(widget.person.id, delta, _reason.text.trim()));
    if (!mounted || !ok) return;
    await widget.onChanged();
    if (mounted) Navigator.pop(context);
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Padding(
      padding: EdgeInsets.fromLTRB(16, 0, 16, 16 + MediaQuery.viewInsetsOf(context).bottom),
      child: SingleChildScrollView(
        child: Column(mainAxisSize: MainAxisSize.min, crossAxisAlignment: CrossAxisAlignment.stretch, children: [
          Text(widget.person.name, style: theme.textTheme.titleLarge),
          Text(l10n.starsCount(widget.person.balance)),
          const SizedBox(height: 12),
          TextField(
            key: const Key('stars-adjust-amount'),
            controller: _amount,
            keyboardType: const TextInputType.numberWithOptions(signed: true),
            decoration: InputDecoration(labelText: l10n.starsAmount),
          ),
          const SizedBox(height: 12),
          TextField(controller: _reason, decoration: InputDecoration(labelText: l10n.starsReason)),
          const SizedBox(height: 12),
          FilledButton(key: const Key('stars-adjust-save'), onPressed: _adjust, child: Text(l10n.starsBonus)),
          const SizedBox(height: 16),
          Text(l10n.starsHistory, style: theme.textTheme.labelLarge),
          FutureBuilder<List<StarEntry>>(
            future: _history,
            builder: (context, snap) {
              if (snap.connectionState != ConnectionState.done) return const Padding(padding: EdgeInsets.all(16), child: HubLoader.small());
              final items = snap.data ?? const <StarEntry>[];
              if (items.isEmpty) return _Muted(l10n.starsNoHistory);
              return Column(children: [for (final e in items.take(30)) _EntryTile(entry: e)]);
            },
          ),
        ]),
      ),
    );
  }
}
