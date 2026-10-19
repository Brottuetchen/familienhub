import 'package:familienhub/models/stars.dart';
import 'package:familienhub/models/task.dart';
import 'package:familienhub/providers/providers.dart';
import 'package:familienhub/screens/stars/stars_screen.dart';
import 'package:familienhub/screens/today/today_screen.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';

import 'helpers.dart';

const _reward = {'id': 1, 'title': '30 Minuten Medienzeit', 'price': 30, 'active': true};
const _dear = {'id': 2, 'title': 'Ausflug in den Freizeitpark', 'price': 200, 'active': true};

FakeBackend _kid({int balance = 42}) {
  final b = FakeBackend();
  addDefaults(b);
  b.json('GET', '/api/auth/me', {'id': 3, 'username': 'kim', 'role': 'child', 'is_admin': false});
  b.json('GET', '/api/modules', {
    'modules': {for (final m in ['today', 'meals', 'tasks', 'calendar', 'shopping']) m: {'enabled': true}},
    'plugins': [],
  });
  b.json('GET', '/api/stars/me', {
    'enabled': true, 'balance': balance, 'reserved': 0, 'available': balance,
    'next_reward': {'id': 2, 'title': 'Ausflug in den Freizeitpark', 'price': 200, 'missing': 200 - balance},
  });
  b.json('GET', '/api/stars/rewards', {'items': [_reward, _dear]});
  b.json('GET', '/api/stars/settings', {'confirm_tasks': false});
  b.json('GET', '/api/stars/requests', {'items': [
    {'id': 7, 'user_id': 3, 'title': 'Eis', 'price': 5, 'status': 'pending'},
    {'id': 6, 'user_id': 3, 'title': 'Kino', 'price': 5, 'status': 'declined'},
  ]});
  b.json('GET', '/api/stars/ledger', {'items': [
    {'id': 1, 'user_id': 3, 'delta': 5, 'kind': 'task', 'status': 'confirmed', 'title': 'Zimmer aufräumen'},
    {'id': 2, 'user_id': 3, 'delta': 3, 'kind': 'task', 'status': 'pending', 'title': 'Müll rausbringen'},
  ]});
  b.json('POST', '/api/stars/requests', {'id': 8});
  b.json('POST', '/api/stars/requests/7/cancel', {'id': 7});
  return b;
}

FakeBackend _parent() {
  final b = _kid();
  b.json('GET', '/api/auth/me', {'id': 1, 'username': 'mia', 'role': 'partner', 'is_admin': false});
  b.json('GET', '/api/stars/me', {'enabled': true, 'balance': 0, 'reserved': 0, 'available': 0,
      'next_reward': null, 'pending': {'requests': 1, 'awards': 1, 'total': 2}});
  b.json('GET', '/api/stars/pending', {
    'requests': [{'id': 7, 'user_id': 3, 'user_name': 'Kim', 'title': 'Eis', 'price': 5, 'status': 'pending'}],
    'awards': [{'id': 9, 'user_id': 3, 'user_name': 'Kim', 'delta': 3, 'kind': 'task', 'status': 'pending', 'title': 'Müll rausbringen'}],
  });
  b.json('GET', '/api/stars/people', {'items': [{'id': 3, 'name': 'Kim', 'role': 'child', 'balance': 42, 'reserved': 0, 'available': 42}]});
  b.json('POST', '/api/stars/requests/7/approve', {'id': 7});
  b.json('POST', '/api/stars/ledger/9/confirm', {'id': 9});
  b.json('PUT', '/api/stars/settings', {'confirm_tasks': true});
  b.json('POST', '/api/stars/rewards', {'id': 3});
  b.json('POST', '/api/stars/adjust', {'balance': 45});
  b.json('GET', '/api/stars/ledger', {'items': []});
  return b;
}

void main() {
  setUp(setUpTestEnv);

  test('models parse the server answers and survive garbage', () {
    final s = StarsSummary.fromJson({
      'enabled': true, 'balance': 5, 'reserved': 2, 'available': 3,
      'next_reward': {'id': 1, 'title': 'Eis', 'price': 9, 'missing': 6}, 'pending': {'total': 4},
    });
    expect(s.enabled && s.balance == 5 && s.available == 3 && s.pending == 4, isTrue);
    expect(s.nextReward?.missing, 6);
    expect(StarsSummary.fromJson('nope').enabled, isFalse);
    expect(Task.fromJson({'uid': 'a', 'title': 'x', 'stars': 4}).stars, 4);
    expect(Task.fromJson({'uid': 'a', 'title': 'x'}).stars, 0);
  });

  test('creating and editing a task sends its stars', () async {
    final b = FakeBackend();
    addDefaults(b);
    b.json('POST', '/api/tasks', {'uid': 'n1', 'title': 'Müll', 'provider': 'hub_tasks', 'stars': 5});
    b.json('PATCH', '/api/tasks/n1', {'uid': 'n1', 'stars': 8});
    final api = b.api();
    await api.createTask(title: 'Müll', provider: 'hub_tasks', account: '1:hub', stars: 5);
    expect(bodyOf(b.sent('POST', '/api/tasks').single)['stars'], 5);
    await api.updateTask(const Task(uid: 'n1', title: 'Müll', provider: 'hub_tasks', account: '1:hub', stars: 5),
        title: 'Müll', notes: '', stars: 8);
    expect(bodyOf(b.sent('PATCH', '/api/tasks/n1').single)['stars'], 8);
  });

  testWidgets('a child sees balance and next reward, requests an affordable reward only', (tester) async {
    await setScreenSize(tester, const Size(420, 1400));
    final b = _kid();
    await tester.pumpWidget(appWith(b.api(), const StarsScreen()));
    await tester.pumpAndSettle();
    expect(find.byKey(const Key('stars-balance')), findsOneWidget);
    expect(find.text('42'), findsOneWidget);
    expect(find.text('noch 158 Sterne'), findsOneWidget);
    expect(tester.widget<FilledButton>(find.byKey(const Key('reward-request-2'))).onPressed, isNull,
        reason: 'not enough stars');
    expect(find.text('Wartet auf Bestätigung'), findsOneWidget, reason: 'pending award shows as such');
    // a child gets no parent controls
    expect(find.byKey(const Key('reward-add')), findsNothing);
    expect(find.byKey(const Key('stars-confirm-tasks')), findsNothing);
    expect(b.sent('GET', '/api/stars/pending'), isEmpty);

    await tester.tap(find.byKey(const Key('reward-request-1')));
    await tester.pumpAndSettle();
    expect(bodyOf(b.sent('POST', '/api/stars/requests').single), {'reward_id': 1});
    await tester.tap(find.text('Zurückziehen'));
    await tester.pumpAndSettle();
    expect(b.sent('POST', '/api/stars/requests/7/cancel'), hasLength(1));
  });

  testWidgets('a parent decides on requests and confirmations and manages rewards', (tester) async {
    await setScreenSize(tester, const Size(420, 1800));
    final b = _parent();
    await tester.pumpWidget(appWith(b.api(), const StarsScreen()));
    await tester.pumpAndSettle();
    await tester.tap(find.descendant(of: find.byKey(const Key('decide-request-7')), matching: find.text('Bewilligen')));
    await tester.pumpAndSettle();
    expect(b.sent('POST', '/api/stars/requests/7/approve'), hasLength(1));
    await tester.tap(find.descendant(of: find.byKey(const Key('decide-award-9')), matching: find.text('Bestätigen')));
    await tester.pumpAndSettle();
    expect(b.sent('POST', '/api/stars/ledger/9/confirm'), hasLength(1));

    await tester.scrollUntilVisible(find.byKey(const Key('stars-confirm-tasks')), 300,
        scrollable: find.byType(Scrollable).first);
    await tester.tap(find.byKey(const Key('stars-confirm-tasks')));
    await tester.pumpAndSettle();
    expect(bodyOf(b.sent('PUT', '/api/stars/settings').single), {'confirm_tasks': true});

    await tester.ensureVisible(find.byKey(const Key('reward-add')));
    await tester.tap(find.byKey(const Key('reward-add')));
    await tester.pumpAndSettle();
    await tester.enterText(find.byKey(const Key('reward-title')), '1 € Taschengeld');
    await tester.enterText(find.byKey(const Key('reward-price')), '20');
    await tester.tap(find.byKey(const Key('reward-save')));
    await tester.pumpAndSettle();
    expect(bodyOf(b.sent('POST', '/api/stars/rewards').single), {'title': '1 € Taschengeld', 'price': 20});
  });

  testWidgets('a parent can give a bonus to a child', (tester) async {
    await setScreenSize(tester, const Size(420, 1800));
    final b = _parent();
    await tester.pumpWidget(appWith(b.api(), const StarsScreen()));
    await tester.pumpAndSettle();
    await tester.ensureVisible(find.byKey(const Key('person-3')));
    await tester.tap(find.byKey(const Key('person-3')));
    await tester.pumpAndSettle();
    await tester.enterText(find.byKey(const Key('stars-adjust-amount')), '3');
    await tester.tap(find.byKey(const Key('stars-adjust-save')));
    await tester.pumpAndSettle();
    expect(bodyOf(b.sent('POST', '/api/stars/adjust').single), {'user_id': 3, 'delta': 3, 'title': ''});
  });

  for (final parent in [false, true]) {
    testWidgets('stars screen (${parent ? 'parent' : 'child'}) fits 360 dp at text scale 2.0', (tester) async {
      await setScreenSize(tester, const Size(360, 900));
      tester.platformDispatcher.textScaleFactorTestValue = 2.0;
      addTearDown(tester.platformDispatcher.clearTextScaleFactorTestValue);
      await tester.pumpWidget(appWith((parent ? _parent() : _kid()).api(), const StarsScreen()));
      await tester.pumpAndSettle();
      expect(find.byKey(const Key('stars-list')), findsOneWidget);
      expect(tester.takeException(), isNull);
    });
  }

  for (final scale in [1.0, 2.0]) {
    testWidgets('Today stars card fits 360 dp at text scale $scale and is hidden without stars use', (tester) async {
      await setScreenSize(tester, const Size(360, 2400));
      tester.platformDispatcher.textScaleFactorTestValue = scale;
      addTearDown(tester.platformDispatcher.clearTextScaleFactorTestValue);
      final b = _kid();
      b.json('GET', '/api/me/today-layout', {'source': 'user', 'cards': [
        {'id': 'stars', 'visible': true, 'size': 'full'},
      ]});
      await tester.pumpWidget(ProviderScope(
        overrides: [apiClientProvider.overrideWithValue(b.api())],
        child: const MaterialApp(locale: Locale('de', 'DE'), home: TodayScreen()),
      ));
      await tester.pumpAndSettle();
      expect(find.byKey(const Key('today-stars')), findsOneWidget);
      expect(find.byKey(const Key('today-stars-balance')), findsOneWidget);
      expect(find.textContaining('Ausflug in den Freizeitpark'), findsOneWidget);
      expect(tester.takeException(), isNull);

      final off = _kid();
      off.json('GET', '/api/stars/me', {'enabled': false, 'balance': 0, 'reserved': 0, 'available': 0, 'next_reward': null});
      await tester.pumpWidget(ProviderScope(
        key: UniqueKey(),
        overrides: [apiClientProvider.overrideWithValue(off.api())],
        child: const MaterialApp(locale: Locale('de', 'DE'), home: TodayScreen()),
      ));
      await tester.pumpAndSettle();
      expect(find.byKey(const Key('today-stars')), findsNothing);
    });
  }

  testWidgets('older server without the stars endpoint: no card, no error', (tester) async {
    await setScreenSize(tester, const Size(420, 2400));
    final b = FakeBackend();
    addDefaults(b);
    await tester.pumpWidget(ProviderScope(
      overrides: [apiClientProvider.overrideWithValue(b.api())],
      child: const MaterialApp(locale: Locale('de', 'DE'), home: TodayScreen()),
    ));
    await tester.pumpAndSettle();
    expect(find.byKey(const Key('today-stars')), findsNothing);
    expect(find.byType(SnackBar), findsNothing);
    expect(tester.takeException(), isNull);
  });
}
