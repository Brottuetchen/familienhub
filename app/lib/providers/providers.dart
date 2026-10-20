import 'dart:async';

import 'package:flutter/foundation.dart' show kIsWeb;
import 'package:flutter/widgets.dart' show AppLifecycleListener;
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../models/account.dart';
import '../models/birthday.dart';
import '../models/calendar_event.dart';
import '../models/common.dart';
import '../models/meals.dart';
import '../models/modules.dart';
import '../models/pending.dart';
import '../models/shopping.dart';
import '../models/stars.dart';
import '../models/task.dart';
import '../models/today.dart';
import '../models/timetable.dart';
import '../models/today_layout.dart';
import '../services/api_client.dart';
import 'cached_read.dart';
import '../services/home_widgets.dart';
import '../services/widget_access.dart';
import '../services/push_service.dart';
import '../services/session_store.dart';
import '../services/web_platform.dart' as webp;
import '../l10n/l10n.dart';

/// In Tests mit einem ApiClient auf MockClient-Basis überschreiben.
final apiClientProvider = Provider<ApiClient>((ref) {
  return ApiClient(store: SecureSessionStore());
});

// ── Sitzung ──────────────────────────────────────────────────────────────────

enum SessionPhase { loading, needsServer, loggedOut, loggedIn }

class SessionState {
  final SessionPhase phase;
  final AppUser? user;
  final String? error;
  /// Gerade das erste Admin-Konto angelegt: Einrichtungs-Assistent statt App zeigen.
  final bool onboarding;

  const SessionState(this.phase, {this.user, this.error, this.onboarding = false});
}

class SessionNotifier extends StateNotifier<SessionState> {
  final ApiClient api;
  final void Function()? onScopeChanged;
  StreamSubscription<void>? _sub;
  int _revision = 0;

  /// Tells [sessionScopeProvider] when the signed-in session ends or the person changes.
  @override
  set state(SessionState value) {
    final before = state;
    final ended = before.phase == SessionPhase.loggedIn &&
        (value.phase == SessionPhase.loggedOut || value.phase == SessionPhase.needsServer);
    final otherPerson = before.user != null && value.user != null && before.user!.id != value.user!.id;
    super.state = value;
    if (ended || otherPerson) onScopeChanged?.call();
  }

  SessionNotifier(this.api, {bool autoStart = true, this.onScopeChanged})
      : super(const SessionState(SessionPhase.loading)) {
    _sub = api.loggedOut.listen((_) {
      unawaited(WidgetAccess.forget()); // Sitzung beendet: keine Inhalte mehr auf dem Startbildschirm
      state = SessionState(SessionPhase.loggedOut,
          error: l10n.sessionExpired);
    });
    if (autoStart) start();
  }

  Future<void> start() async {
    final revision = ++_revision;
    // Web-App: Server ist immer die Seite selbst
    final origin = kIsWeb ? webp.pageOrigin() : null;
    if (origin != null && await api.store.baseUrl() != origin) {
      if (!mounted || revision != _revision) return;
      await api.setServer(origin);
    }
    final base = await api.store.baseUrl();
    if (!mounted || revision != _revision) return;
    if (base == null) {
      state = const SessionState(SessionPhase.needsServer);
      return;
    }
    final token = await api.store.accessToken();
    if (!mounted || revision != _revision) return;
    if (token == null) {
      state = const SessionState(SessionPhase.loggedOut);
      return;
    }
    try {
      final user = await api.me();
      if (mounted && revision == _revision) {
        state = SessionState(SessionPhase.loggedIn, user: user);
      }
    } catch (e) {
      // Ohne Netz trotzdem rein: die Daten kommen dann aus dem Cache.
      final offline = ApiClient.isNetworkError(e) && await api.store.accessToken() != null;
      if (!mounted || revision != _revision) return;
      state = SessionState(offline ? SessionPhase.loggedIn : SessionPhase.loggedOut);
    }
  }

  Future<void> setServer(String url) async {
    final revision = ++_revision;
    await api.setServer(url);
    if (mounted && revision == _revision) state = const SessionState(SessionPhase.loggedOut);
  }

  void changeServer() {
    _revision++;
    state = const SessionState(SessionPhase.needsServer);
  }

  Future<void> login(String username, String password) async {
    final revision = ++_revision;
    final user = await api.login(username, password);
    if (mounted && revision == _revision) state = SessionState(SessionPhase.loggedIn, user: user);
  }

  /// Ersteinrichtung: erstes Admin-Konto anlegen, anmelden und den Assistenten starten.
  Future<void> createFirstAdmin({
    String? code,
    required String username,
    required String email,
    required String password,
    String? displayName,
  }) async {
    final revision = ++_revision;
    final user = await api.createFirstAdmin(
        code: code, username: username, email: email, password: password, displayName: displayName);
    if (mounted && revision == _revision) state = SessionState(SessionPhase.loggedIn, user: user, onboarding: true);
  }

  /// Einladung einlösen: eigenes Passwort setzen und anmelden.
  Future<void> acceptInvite({required String code, required String password}) async {
    final revision = ++_revision;
    final user = await api.acceptInvite(code: code, password: password);
    if (mounted && revision == _revision) state = SessionState(SessionPhase.loggedIn, user: user);
  }

  /// Assistent beendet: weiter in die App.
  void finishOnboarding() {
    if (state.phase == SessionPhase.loggedIn) state = SessionState(SessionPhase.loggedIn, user: state.user);
  }

  Future<void> loginWithCode(String code) async {
    final revision = ++_revision;
    final user = await api.exchangeOidcCode(code);
    if (mounted && revision == _revision) state = SessionState(SessionPhase.loggedIn, user: user);
  }

  /// Nach Profiländerung: neue Nutzerdaten übernehmen (Name, Farbe, Bild) ohne neu anzumelden.
  void updateUser(AppUser user) {
    if (state.phase == SessionPhase.loggedIn) {
      state = SessionState(SessionPhase.loggedIn, user: user, onboarding: state.onboarding);
    }
  }

  Future<void> logout() async {
    final revision = ++_revision;
    await WidgetAccess.revoke(api); // Widget-Zugang widerrufen und Widgets leeren, solange die Anmeldung gilt
    await api.logout();
    if (mounted && revision == _revision) state = const SessionState(SessionPhase.loggedOut);
  }

  @override
  void dispose() {
    _sub?.cancel();
    super.dispose();
  }
}

final sessionProvider = StateNotifierProvider<SessionNotifier, SessionState>(
  (ref) => SessionNotifier(ref.watch(apiClientProvider),
      onScopeChanged: () => Future.microtask(() {
        try { ref.read(sessionScopeProvider.notifier).state++; } catch (_) {} // container already disposed
      })),
);

/// Counter that moves whenever a signed-in session ends (logout, expiry, server switch) or another person
/// signs in. Every provider that holds server or user data and is not
/// auto-disposed watches this, so a server switch, logout or login as someone else drops the old state instead
/// of showing it (modules, lists, tasks, accounts of the previous server/user) for the new one (#67).
final sessionScopeProvider = StateProvider<int>((ref) => 0);

/// Rollenstufe der Anmeldung. Ohne bekannte Rolle (offline gestartet) wie Partner:
/// Der Server prüft ohnehin und lehnt Unerlaubtes mit einer Meldung ab.
final roleLevelProvider = Provider<int>((ref) => ref.watch(sessionProvider.select((s) => s.user?.roleLevel ?? 2)));

/// Ab Kind: abhaken, Wünsche, eigene Konten verbinden, Einkauf löschen.
final canActProvider = Provider<bool>((ref) => ref.watch(roleLevelProvider) >= 1);

/// Ab Partner: Aufgaben, Termine, Essensplan, Rezepte und Familien-Erinnerungen anlegen und ändern.
final canEditProvider = Provider<bool>((ref) => ref.watch(roleLevelProvider) >= 2);

// ── Navigation ───────────────────────────────────────────────────────────────

enum AppTab { today, calendar, tasks, shopping, meals, more }

final tabProvider = StateProvider<AppTab>((ref) => AppTab.today);

/// A link shared into the app (PWA share target): the main screen opens "Import from link" with it.
final shareImportUrlProvider = StateProvider<String?>((ref) => null);

/// First http(s) link in shared text (browsers often put the link into the text field), or null.
String? extractSharedUrl(Iterable<String?> parts) {
  for (final part in parts) {
    final m = RegExp(r'https?://[^\s<>"]+', caseSensitive: false).firstMatch(part ?? '');
    if (m != null) return m.group(0);
  }
  return null;
}
final taskViewProvider = StateProvider<TaskView>((ref) => TaskView.mine);

/// Ziel aus einer Push-Mitteilung (`data.route`), z. B. `/tasks?view=for_me`.
void openRoute(WidgetRef ref, String route) {
  final uri = Uri.tryParse(route);
  if (uri == null) return;
  final segment = uri.pathSegments.isEmpty ? '' : uri.pathSegments.first;
  final tab = switch (segment) {
    'tasks' => AppTab.tasks,
    'calendar' => AppTab.calendar,
    'shopping' => AppTab.shopping,
    'meals' => AppTab.meals,
    'reminders' || 'more' => AppTab.more,
    _ => AppTab.today,
  };
  if (tab == AppTab.tasks) {
    ref.read(taskViewProvider.notifier).state =
        TaskView.fromApi(uri.queryParameters['view']);
  }
  ref.read(tabProvider.notifier).state = tab;
}

// ── Module ───────────────────────────────────────────────────────────────────

/// Aktive Bereiche. Fehler/Offline ohne Cache → alles zeigen.
final modulesProvider = StateNotifierProvider<CachedRead<AppModules>, AsyncValue<ApiResult<AppModules>>>((ref) => _cachedRead(
  ref, 'modules', (j) => AppModules.fromJson(j as Map<String, dynamic>), (api) => api.modules()));

/// Synchroner Zugriff für die Oberfläche (während des Ladens: alles).
final appModulesProvider = Provider<AppModules>(
    (ref) => ref.watch(modulesProvider).valueOrNull?.data ?? AppModules.all);

// ── Daten ────────────────────────────────────────────────────────────────────

CachedRead<T> _cachedRead<T>(Ref ref, String key, T Function(dynamic) parse,
    Future<ApiResult<T>> Function(ApiClient) load) {
  ref.watch(sessionScopeProvider);
  final read = CachedRead(ref.watch(apiClientProvider), key, parse, load);
  // Zurück zum Reiter: vorhandene Daten bleiben synchron, nur HTTP läuft neu.
  ref.onResume(() => read.refresh().ignore());
  return read;
}

/// Gemerkte Offline-Änderungen (#32). Beim Zurückkehren in die App wird sofort gesendet.
final pendingChangesProvider = StreamProvider<List<PendingChange>>((ref) async* {
  ref.watch(sessionScopeProvider);
  final api = ref.watch(apiClientProvider);
  final listener = AppLifecycleListener(onResume: () => api.flushPending().ignore());
  ref.onDispose(listener.dispose);
  yield await api.loadPending();
  yield* api.pendingChanges;
});

final todayProvider = StateNotifierProvider<CachedRead<TodayData>, AsyncValue<ApiResult<TodayData>>>((ref) => _cachedRead(
  ref, 'today', (j) => TodayData.fromJson(j as Map<String, dynamic>), (api) async {
    final result = await api.today();
    if (!result.fromCache) unawaited(HomeWidgets.updateToday(result.data));
    return result;
  }));

/// Own arrangement of Today. Errors (older server, offline) are not shown: callers fall back to the built-in one.
final todayLayoutProvider = StateNotifierProvider<CachedRead<TodayLayout>, AsyncValue<ApiResult<TodayLayout>>>(
  (ref) => _cachedRead(ref, 'layout:today', TodayLayout.fromJson, (api) => api.todayLayout()));

/// Own stars for the Today card and the stars screen (errors fall back to "no stars feature").
final starsProvider = StateNotifierProvider<CachedRead<StarsSummary>, AsyncValue<ApiResult<StarsSummary>>>(
  (ref) => _cachedRead(ref, 'stars:me', StarsSummary.fromJson, (api) => api.starsMe()));

final tasksProvider = StateNotifierProvider.family<CachedRead<SourceResult<Task>>, AsyncValue<ApiResult<SourceResult<Task>>>, TaskView>(
  (ref, view) => _cachedRead(ref, 'tasks:${view.apiName}',
    (j) => SourceResult.fromJson(j as Map<String, dynamic>, Task.fromJson),
    (api) => api.tasks(view)));

final peopleProvider = FutureProvider.autoDispose<List<Person>>(
    (ref) => ref.watch(apiClientProvider).people());

final shoppingProvider = StateNotifierProvider<CachedRead<ShoppingData>, AsyncValue<ApiResult<ShoppingData>>>((ref) => _cachedRead(
  ref, 'shopping', (j) => ShoppingData.fromJson(j as Map<String, dynamic>), (api) async {
    final result = await api.shopping();
    if (!result.fromCache) unawaited(HomeWidgets.updateShopping(result.data));
    return result;
  }));

final mealsProvider = StateNotifierProvider.family<CachedRead<MealWeek>, AsyncValue<ApiResult<MealWeek>>, String>(
  (ref, week) => _cachedRead(ref, 'meals:$week',
    (j) => MealWeek.fromJson(j as Map<String, dynamic>), (api) => api.meals(week)));

final eventsProvider = StateNotifierProvider<CachedRead<List<CalendarEvent>>, AsyncValue<ApiResult<List<CalendarEvent>>>>((ref) => _cachedRead(
  ref, 'events:30', (j) => (j as List).whereType<Map<String, dynamic>>().map(CalendarEvent.fromJson).toList(),
  (api) => api.events(days: 30)));

/// Events of a grid range, key "YYYY-MM-DD:days" (month: 42 days from the first grid Monday, week: 7).
final eventsRangeProvider = StateNotifierProvider.family<CachedRead<List<CalendarEvent>>, AsyncValue<ApiResult<List<CalendarEvent>>>, String>(
  (ref, key) {
    final parts = key.split(':');
    return _cachedRead(ref, 'events:$key',
        (j) => (j as List).whereType<Map<String, dynamic>>().map(CalendarEvent.fromJson).toList(),
        (api) => api.eventsRange(DateTime.parse(parts[0]), int.parse(parts[1])));
  });

final timetableChildrenProvider = FutureProvider.autoDispose<List<TimetableChild>>(
    (ref) => ref.watch(apiClientProvider).timetableChildren());

final timetableProvider = FutureProvider.autoDispose.family<TimetableData, int>(
    (ref, childId) => ref.watch(apiClientProvider).timetable(childId));

/// Calendar week of a child with real dates: [start] is any day of the week.
final timetableWeekProvider = FutureProvider.autoDispose.family<TimetableWeek, ({int childId, DateTime start})>(
    (ref, key) => ref.watch(apiClientProvider).timetableWeek(key.childId, key.start));

final timetableSourcesProvider = FutureProvider.autoDispose<TimetableSources>(
    (ref) => ref.watch(apiClientProvider).timetableSources());

final remindersProvider = FutureProvider.autoDispose<List<Reminder>>(
    (ref) => ref.watch(apiClientProvider).reminders());

final birthdaysProvider = FutureProvider.autoDispose<List<Birthday>>(
    (ref) => ref.watch(apiClientProvider).birthdays());

final giftIdeasProvider = FutureProvider.autoDispose.family<List<GiftIdea>, int>(
    (ref, birthdayId) => ref.watch(apiClientProvider).giftIdeas(birthdayId));

final devicesProvider = FutureProvider.autoDispose<List<Device>>(
    (ref) => ref.watch(apiClientProvider).devices());

final pushServiceProvider = Provider<PushService>(
    (ref) => PushService(ref.watch(apiClientProvider)));


/// Preferred task place of the person (profile setting); null while unknown or on an older server.
final taskPlaceProvider = FutureProvider.autoDispose<TaskPlaceInfo?>((ref) {
  ref.watch(sessionProvider.select((s) => s.user?.id));
  return ref.watch(apiClientProvider).taskPlace();
});

final taskAccountsProvider = FutureProvider<List<TaskProviderInfo>>((ref) {
  ref.watch(sessionScopeProvider);
  return ref.watch(apiClientProvider).taskProviders();
});
