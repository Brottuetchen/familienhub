import 'dart:async';

import 'package:app_links/app_links.dart';
import 'package:flutter/foundation.dart' show LicenseEntryWithLineBreaks, LicenseRegistry, kIsWeb;
import 'package:flutter/material.dart';
import 'package:flutter/services.dart' show rootBundle;
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:intl/date_symbol_data_local.dart';

import 'core/theme/app_theme.dart';
import 'l10n/l10n.dart';
import 'providers/providers.dart';
import 'providers/theme_provider.dart';
import 'screens/auth/login_screen.dart';
import 'screens/auth/server_setup_screen.dart';
import 'screens/main_shell.dart';
import 'services/error_reporter.dart';
import 'screens/setup/setup_wizard_screen.dart';
import 'services/web_platform.dart' as webp;
import 'widgets/common.dart';
import 'widgets/hub_background.dart';

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  await initializeDateFormatting();
  await loadAppLanguage();
  // Lizenzen der mitgelieferten Theme-Schriften (SIL OFL) in der Lizenzübersicht
  LicenseRegistry.addLicense(() async* {
    for (final family in ['PixelifySans', 'SpaceGrotesk', 'JetBrainsMono']) {
      yield LicenseEntryWithLineBreaks([family], await rootBundle.loadString('assets/fonts/$family/OFL.txt'));
    }
  });
  ErrorReporter.install(); // unerwartete Fehler ins Protokoll der Verwaltung (nur angemeldet)
  runApp(const ProviderScope(child: FamilienhubApp()));
}

class FamilienhubApp extends ConsumerWidget {
  const FamilienhubApp({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final spec = ref.watch(themeChoiceProvider);
    final mode = ref.watch(themeModeProvider);
    final language = resolveLanguage(ref.watch(languageChoiceProvider));
    setAppLanguage(language);
    ErrorReporter.api = ref.read(apiClientProvider);
    return MaterialApp(
      // Sprachwechsel baut alles neu auf: Texte kommen auch aus `l10n` ohne BuildContext
      key: ValueKey('app-$language'),
      title: 'Familienhub',
      // Hell/Dunkel/Automatisch: jede Fassung des Themes; ohne Variante bleibt es bei der Grundfassung
      theme: spec == null ? AppTheme.dark : AppTheme.fromSpec(spec.forBrightness(Brightness.light)),
      darkTheme: spec == null ? AppTheme.dark : AppTheme.fromSpec(spec.forBrightness(Brightness.dark)),
      themeMode: mode,
      debugShowCheckedModeBanner: false,
      locale: Locale(language),
      supportedLocales: AppLocalizations.supportedLocales,
      localizationsDelegates: AppLocalizations.localizationsDelegates,
      builder: (context, child) => HubBackground(child: child ?? const SizedBox.shrink()),
      home: const AuthGate(),
    );
  }
}

/// Meldung zu `familienhub://auth?error=…` aus dem Backend.
String oidcErrorText(String code) => switch (code) {
      'unknown_user' => l10n.oidcUnknownUser,
      'disabled' => l10n.oidcDisabled,
      'cancelled' => l10n.oidcCancelled,
      'expired' => l10n.oidcExpired,
      _ => l10n.oidcFailed,
    };

/// Entscheidet zwischen Server-Einrichtung, Anmeldung und App.
/// Nimmt außerdem den Rücksprung von Authentik (`familienhub://auth?code=…`) entgegen.
class AuthGate extends ConsumerStatefulWidget {
  const AuthGate({super.key});

  @override
  ConsumerState<AuthGate> createState() => _AuthGateState();
}

class _AuthGateState extends ConsumerState<AuthGate> {
  StreamSubscription<Uri>? _links;
  bool _exchanging = false;

  @override
  void initState() {
    super.initState();
    if (kIsWeb) {
      // Rücksprung von Authentik bzw. Tipp auf eine Mitteilung: ?oidc_code=… / ?oidc_error=… / ?route=…
      final q = webp.startQuery();
      webp.clearStartQuery();
      WidgetsBinding.instance.addPostFrameCallback((_) {
        if (q['oidc_error'] != null) {
          _handleLink(Uri(scheme: 'familienhub', host: 'auth', queryParameters: {'error': q['oidc_error']!}));
        } else if (q['oidc_code'] != null) {
          _handleLink(Uri(scheme: 'familienhub', host: 'auth', queryParameters: {'code': q['oidc_code']!}));
        }
        if (q['route'] != null) openRoute(ref, q['route']!);
        final shared = extractSharedUrl([q['share_url'], q['share_text'], q['share_title']]);
        if (shared != null) ref.read(shareImportUrlProvider.notifier).state = shared;
      });
      return;
    }
    try {
      final appLinks = AppLinks();
      _links = appLinks.uriLinkStream.listen(_handleLink, onError: (_) {});
    } catch (_) {
      // Keine Plattform-Unterstützung (z. B. Tests)
    }
  }

  @override
  void dispose() {
    _links?.cancel();
    super.dispose();
  }

  Future<void> _handleLink(Uri uri) async {
    if (uri.scheme == 'familienhub' && uri.host == 'open') {
      // Widget/Verknüpfung: familienhub://open?route=/shopping
      final route = uri.queryParameters['route'];
      if (route != null) openRoute(ref, route);
      return;
    }
    if (uri.scheme != 'familienhub' || uri.host != 'auth') return;
    final error = uri.queryParameters['error'];
    if (error != null) {
      if (mounted) showInfo(context, oidcErrorText(error));
      return;
    }
    final code = uri.queryParameters['code'];
    if (code == null || code.isEmpty || _exchanging) return;
    setState(() => _exchanging = true);
    try {
      await ref.read(sessionProvider.notifier).loginWithCode(code);
    } catch (e) {
      if (mounted) showError(context, e);
    } finally {
      if (mounted) setState(() => _exchanging = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final session = ref.watch(sessionProvider);
    if (_exchanging) {
      return const Scaffold(body: Center(child: HubLoader()));
    }
    return switch (session.phase) {
      SessionPhase.loading =>
        const Scaffold(body: Center(child: HubLoader())),
      SessionPhase.needsServer => const ServerSetupScreen(),
      SessionPhase.loggedOut => LoginScreen(message: session.error),
      SessionPhase.loggedIn => session.onboarding ? const SetupWizardScreen() : const MainShell(),
    };
  }
}
