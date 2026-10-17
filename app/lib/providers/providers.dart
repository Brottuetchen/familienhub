import 'dart:async';

import 'package:flutter/foundation.dart' show kIsWeb;
import 'package:flutter/widgets.dart' show AppLifecycleListener;
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../models/account.dart';
import '../models/calendar_event.dart';
import '../models/common.dart';
import '../models/meals.dart';
import '../models/modules.dart';
import '../models/pending.dart';
import '../models/shopping.dart';
import '../models/task.dart';
import '../models/today.dart';
import '../services/api_client.dart';
import 'cached_read.dart';
import '../services/home_widgets.dart';
import '../services/widget_access.dart';
import '../services/push_service.dart';
import '../services/session_store.dart';
import '../services/web_platform.dart' as webp;

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

  const SessionState(this.phase, {this.user, this.error});
}

class SessionNotifier extends StateNotifier<SessionState> {
  final ApiClient api;
  StreamSubscription<void>? _sub;
  int _revision = 0;

  SessionNotifier(this.api, {bool autoStart = true})
      : super(const SessionState(SessionPhase.loading)) {
    _sub = api.loggedOut.listen((_) {
      unawaited(WidgetAccess.forget()); // Sitzung beendet: keine Inhalte mehr auf dem Startbildschirm
      state = const SessionState(SessionPhase.loggedOut,
          error: 'Sitzung abgelaufen, bitte neu anmelden');
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

  Future<void> loginWithCode(String code) async {
    final revision = ++_revision;
    final user = await api.exchangeOidcCode(code);
    if (mounted && revision == _revision) state = SessionState(SessionPhase.loggedIn, user: user);
  }

  /// Nach Profiländerung: neue Nutzerdaten übernehmen (Name, Farbe, Bild) ohne neu anzumelden.
  void updateUser(AppUser user) {
    if (state.phase == SessionPhase.loggedIn) state = SessionState(SessionPhase.loggedIn, user: user);
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
  (ref) => SessionNotifier(ref.watch(apiClientProvider)),
);

// ── Navigation ───────────────────────────────────────────────────────────────

enum AppTab { today, calendar, tasks, shopping, meals, more }

final tabProvider = StateProvider<AppTab>((ref) => AppTab.today);
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
  final read = CachedRead(ref.watch(apiClientProvider), key, parse, load);
  // Zurück zum Reiter: vorhandene Daten bleiben synchron, nur HTTP läuft neu.
  ref.onResume(() => read.refresh().ignore());
  return read;
}

/// Gemerkte Offline-Änderungen (#32). Beim Zurückkehren in die App wird sofort gesendet.
final pendingChangesProvider = StreamProvider<List<PendingChange>>((ref) async* {
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

final remindersProvider = FutureProvider.autoDispose<List<Reminder>>(
    (ref) => ref.watch(apiClientProvider).reminders());

final devicesProvider = FutureProvider.autoDispose<List<Device>>(
    (ref) => ref.watch(apiClientProvider).devices());

final pushServiceProvider = Provider<PushService>(
    (ref) => PushService(ref.watch(apiClientProvider)));


final taskAccountsProvider = FutureProvider<List<TaskProviderInfo>>((ref) {
  ref.watch(sessionProvider.select((s) => s.user?.id));
  return ref.watch(apiClientProvider).taskProviders();
});
