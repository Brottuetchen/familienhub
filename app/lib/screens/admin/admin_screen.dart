import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../models/admin.dart';
import '../../providers/providers.dart';
import '../../widgets/common.dart';
import '../more/appearance_screen.dart';
import '../more/plugins_admin_screen.dart';
import '../more/service_keys_screen.dart';
import '../setup/setup_wizard_screen.dart';
import 'admin_feedback_screen.dart';
import 'admin_house_screen.dart';
import 'admin_log_screen.dart';
import 'admin_users_screen.dart';
import '../../l10n/l10n.dart';
import 'sources_screen.dart';

final adminOverviewProvider =
    FutureProvider.autoDispose<AdminOverview>((ref) => ref.watch(apiClientProvider).adminOverview());

/// Verwaltung: alles für Admins an einer Stelle. Oben der Systemzustand, darunter die Bereiche.
class AdminScreen extends ConsumerWidget {
  const AdminScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final overview = ref.watch(adminOverviewProvider);
    void open(Widget page) async {
      await Navigator.of(context).push(MaterialPageRoute(builder: (_) => page));
      ref.invalidate(adminOverviewProvider);
    }

    return Scaffold(
      appBar: AppBar(title: Text(l10n.administration)),
      body: HubRefresh(
        onRefresh: () => ref.refresh(adminOverviewProvider.future),
        child: ListView(
          physics: const AlwaysScrollableScrollPhysics(),
          padding: const EdgeInsets.only(bottom: 24),
          children: [
            Padding(
              padding: const EdgeInsets.all(16),
              child: overview.when(
                loading: () => const Center(child: HubLoader()),
                error: (e, _) => ErrorView(error: e, onRetry: () => ref.invalidate(adminOverviewProvider)),
                data: (o) => _OverviewCard(overview: o),
              ),
            ),
            _Area(
              key: const Key('admin-wizard'),
              icon: Icons.auto_fix_high_outlined,
              title: l10n.setupWizard,
              subtitle: l10n.setupWizardHint,
              onTap: () => open(const SetupWizardScreen(standalone: true)),
            ),
            _Area(
              key: const Key('admin-sources'),
              icon: Icons.alt_route,
              title: l10n.sourcesAdmin,
              subtitle: l10n.sourcesAdminHint,
              onTap: () => open(const SourcesScreen()),
            ),
            _Area(
              key: const Key('admin-users'),
              icon: Icons.people_outline,
              title: l10n.familyRoles,
              subtitle: overview.valueOrNull == null ? l10n.familyRolesHint : l10n.activeCount(overview.value!.activeUsers),
              onTap: () => open(const AdminUsersScreen()),
            ),
            _Area(
              key: const Key('admin-house'),
              icon: Icons.home_outlined,
              title: l10n.house,
              subtitle: l10n.houseAdminHint,
              onTap: () => open(const AdminHouseScreen()),
            ),
            _Area(
              key: const Key('admin-plugins'),
              icon: Icons.extension_outlined,
              title: l10n.pluginsAccess,
              subtitle: l10n.pluginsHint,
              onTap: () => open(const PluginsAdminScreen()),
            ),
            _Area(
              icon: Icons.vpn_key_outlined,
              title: l10n.serviceKeys,
              subtitle: l10n.serviceKeysHint,
              onTap: () => open(const ServiceKeysScreen()),
            ),
            _Area(
              icon: Icons.palette_outlined,
              title: l10n.themes,
              subtitle: l10n.themesHint,
              onTap: () => open(const AppearanceScreen()),
            ),
            _Area(
              key: const Key('admin-feedback'),
              icon: Icons.chat_bubble_outline,
              title: l10n.feedback,
              subtitle: l10n.feedbackAdminHint,
              onTap: () => open(const AdminFeedbackScreen()),
            ),
            _Area(
              key: const Key('admin-log'),
              icon: Icons.receipt_long_outlined,
              title: l10n.log,
              subtitle: l10n.logHint,
              onTap: () => open(const AdminLogScreen()),
            ),
          ],
        ),
      ),
    );
  }
}

class _Area extends StatelessWidget {
  final IconData icon;
  final String title;
  final String subtitle;
  final VoidCallback onTap;
  const _Area({super.key, required this.icon, required this.title, required this.subtitle, required this.onTap});

  @override
  Widget build(BuildContext context) => ListTile(
        leading: Icon(icon),
        title: Text(title),
        subtitle: Text(subtitle),
        trailing: const Icon(Icons.chevron_right),
        onTap: onTap,
      );
}

/// Ampel je Plugin: grün erreichbar, rot Problem, grau aus/nicht eingerichtet.
class _OverviewCard extends StatelessWidget {
  final AdminOverview overview;
  const _OverviewCard({required this.overview});

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final problems = overview.problems;
    return SectionCard(
      key: const Key('admin-overview'),
      icon: problems == 0 ? Icons.check_circle_outline : Icons.error_outline,
      title: l10n.problemsCount(problems),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        for (final p in overview.plugins)
          Padding(
            key: ValueKey('health-${p.id}'),
            padding: const EdgeInsets.symmetric(vertical: 4),
            child: Row(children: [
              _Dot(status: p.status),
              const SizedBox(width: 10),
              Expanded(child: Text(p.name, style: theme.textTheme.bodyMedium?.copyWith(fontWeight: FontWeight.w600))),
              Flexible(
                child: Text(
                  p.status == 'ok' && p.latencyMs != null ? l10n.healthLine(p.message, p.latencyMs!) : p.message,
                  textAlign: TextAlign.end,
                  style: theme.textTheme.bodySmall?.copyWith(color: theme.colorScheme.onSurfaceVariant),
                ),
              ),
            ]),
          ),
        const Divider(height: 20),
        Text(
          [
            l10n.serverVersion(overview.version),
            overview.fcm ? l10n.pushAndroidDevices(overview.fcmDevices) : l10n.pushAndroidOff,
            if (overview.webpush) l10n.webPushDevices(overview.webpushDevices),
          ].join(' · '),
          style: theme.textTheme.bodySmall?.copyWith(color: theme.colorScheme.onSurfaceVariant),
        ),
      ]),
    );
  }
}

class _Dot extends StatelessWidget {
  final String status;
  const _Dot({required this.status});

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final color = switch (status) {
      'ok' => Colors.green,
      'error' => scheme.error,
      'unknown' => Colors.amber,
      _ => scheme.outline,
    };
    return Container(width: 10, height: 10, decoration: BoxDecoration(color: color, shape: BoxShape.circle));
  }
}
