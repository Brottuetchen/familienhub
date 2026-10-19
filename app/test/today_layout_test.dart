import 'package:familienhub/core/theme/app_theme.dart';
import 'package:familienhub/models/themes.dart';
import 'package:familienhub/providers/providers.dart';
import 'package:familienhub/screens/today/today_screen.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';

import 'helpers.dart';

const _bento = ThemeSpec(id: 'builtin:clean-cards', name: 'Clean Cards', colors: {
  'primary': '#2563EB', 'secondary': '#10B981', 'background': '#EEF2F8', 'surface': '#FFFFFF',
  'surfaceHigh': '#F1F5F9', 'border': '#E2E8F0',
}, style: {'layout': 'bento', 'card': {'radius': 24, 'border': 0, 'shadow': 'soft'}});

FakeBackend _backend({Object? layout, int layoutStatus = 200}) {
  final b = FakeBackend();
  addDefaults(b);
  b.json('GET', '/api/modules', {
    'modules': {for (final m in ['today', 'meals', 'tasks', 'calendar', 'shopping']) m: {'enabled': true}},
    'plugins': [],
  });
  b.json('GET', '/api/today', {
    'date': '2026-10-19',
    'events': [],
    'tasks': {'status': 'ok', 'error': null, 'items': []},
    'meals': [],
    'shopping_open': 0,
    'reminders': [],
  });
  if (layout != null) b.json('GET', '/api/me/today-layout', layout, status: layoutStatus);
  b.json('PUT', '/api/me/today-layout', {'cards': [], 'source': 'user'});
  b.json('DELETE', '/api/me/today-layout', {'cards': [], 'source': 'builtin'});
  b.json('PUT', '/api/admin/today-layout', {'cards': [], 'source': 'family'});
  return b;
}

Map<String, dynamic> _layout(List<List<Object>> cards, {String source = 'user'}) => {
      'source': source,
      'cards': [
        for (final c in cards) {'id': c[0], 'visible': c.length < 2 || c[1] as bool, 'size': c.length > 2 ? c[2] : 'full'}
      ],
    };

Widget _app(FakeBackend b, {ThemeSpec? spec}) => ProviderScope(
      overrides: [apiClientProvider.overrideWithValue(b.api())],
      child: MaterialApp(
        locale: const Locale('de', 'DE'),
        theme: spec == null ? AppTheme.dark : AppTheme.fromSpec(spec),
        home: const TodayScreen(),
      ),
    );

const _keys = ['today-tasks', 'today-meals', 'today-shopping', 'today-events'];

double _y(WidgetTester t, String key) => t.getTopLeft(find.byKey(Key(key))).dy;

void main() {
  setUp(setUpTestEnv);

  testWidgets('without a saved layout the original order stays', (tester) async {
    await setScreenSize(tester, const Size(420, 2400));
    await tester.pumpWidget(_app(_backend()));
    await tester.pumpAndSettle();
    expect(_y(tester, 'today-tasks'), lessThan(_y(tester, 'today-meals')));
    expect(_y(tester, 'today-meals'), lessThan(_y(tester, 'today-shopping')));
    expect(_y(tester, 'today-shopping'), lessThan(_y(tester, 'today-events')));
  });

  testWidgets('a hidden card is not shown', (tester) async {
    await setScreenSize(tester, const Size(420, 2400));
    final b = _backend(layout: _layout([['tasks'], ['meals', false], ['shopping'], ['events']]));
    await tester.pumpWidget(_app(b));
    await tester.pumpAndSettle();
    expect(find.byKey(const Key('today-meals')), findsNothing);
    expect(find.byKey(const Key('today-tasks')), findsOneWidget);
  });

  testWidgets('the saved order is applied', (tester) async {
    await setScreenSize(tester, const Size(420, 2400));
    final b = _backend(layout: _layout([['events'], ['shopping'], ['meals'], ['tasks']]));
    await tester.pumpWidget(_app(b));
    await tester.pumpAndSettle();
    expect(_y(tester, 'today-events'), lessThan(_y(tester, 'today-shopping')));
    expect(_y(tester, 'today-shopping'), lessThan(_y(tester, 'today-meals')));
    expect(_y(tester, 'today-meals'), lessThan(_y(tester, 'today-tasks')));
  });

  testWidgets('half cards sit side by side in the bento theme', (tester) async {
    await setScreenSize(tester, const Size(420, 2400));
    final b = _backend(layout: _layout([
      ['meals', true, 'half'], ['tasks', true, 'half'], ['shopping'], ['events'],
    ]));
    await tester.pumpWidget(_app(b, spec: _bento));
    await tester.pumpAndSettle();
    expect(_y(tester, 'today-meals'), _y(tester, 'today-tasks'));
    expect(tester.getTopLeft(find.byKey(const Key('today-tasks'))).dx,
        greaterThan(tester.getTopLeft(find.byKey(const Key('today-meals'))).dx));
    expect(_y(tester, 'today-shopping'), greaterThan(_y(tester, 'today-meals')));
  });

  for (final status in [404, 500]) {
    testWidgets('layout endpoint failing with $status falls back silently', (tester) async {
      await setScreenSize(tester, const Size(420, 2400));
      final b = _backend(layout: {'detail': 'nope'}, layoutStatus: status);
      await tester.pumpWidget(_app(b));
      await tester.pumpAndSettle();
      for (final k in _keys) {
        expect(find.byKey(Key(k)), findsOneWidget);
      }
      expect(find.byType(SnackBar), findsNothing);
      expect(tester.takeException(), isNull);
    });
  }

  testWidgets('the editor saves the arrangement via PUT', (tester) async {
    await setScreenSize(tester, const Size(420, 2400));
    final b = _backend();
    await tester.pumpWidget(_app(b));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const Key('today-customise')));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const Key('layout-visible-meals')));
    await tester.pump();
    await tester.drag(find.byIcon(Icons.drag_handle).first, const Offset(0, 130));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const Key('today-layout-save')));
    await tester.pumpAndSettle();
    final sent = bodyOf(b.sent('PUT', '/api/me/today-layout').single)['cards'] as List;
    final ids = [for (final c in sent) (c as Map)['id']];
    expect(ids.toSet(), {'tasks', 'shopping', 'events', 'meals', 'reminders', 'house'});
    expect(ids.first, isNot('tasks'), reason: 'tasks was dragged down');
    expect((sent.firstWhere((c) => (c as Map)['id'] == 'meals') as Map)['visible'], isFalse);
    expect(find.byKey(const Key('today-layout-save')), findsNothing, reason: 'editor closed');
  });

  testWidgets('admin can save the family default, reset deletes the own layout', (tester) async {
    await setScreenSize(tester, const Size(420, 2400));
    final b = _backend();
    await tester.pumpWidget(_app(b));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const Key('today-customise')));
    await tester.pumpAndSettle();
    await tester.ensureVisible(find.byKey(const Key('today-layout-family')));
    await tester.tap(find.byKey(const Key('today-layout-family')));
    await tester.pumpAndSettle();
    expect(b.sent('PUT', '/api/admin/today-layout'), hasLength(1));
    await tester.tap(find.byKey(const Key('today-layout-reset')));
    await tester.pumpAndSettle();
    expect(b.sent('DELETE', '/api/me/today-layout'), hasLength(1));
  });

  for (final spec in [null, _bento]) {
    testWidgets('screen and editor fit 360 dp at text scale 2.0 (${spec == null ? 'plain' : 'bento'})', (tester) async {
      await setScreenSize(tester, const Size(360, 2400));
      tester.platformDispatcher.textScaleFactorTestValue = 2.0;
      addTearDown(tester.platformDispatcher.clearTextScaleFactorTestValue);
      await tester.pumpWidget(_app(_backend(), spec: spec));
      await tester.pumpAndSettle();
      expect(tester.takeException(), isNull);
      await tester.tap(find.byKey(const Key('today-customise')));
      await tester.pumpAndSettle();
      expect(find.byKey(const Key('layout-visible-tasks')), findsOneWidget);
      expect(tester.takeException(), isNull);
    });
  }
}
