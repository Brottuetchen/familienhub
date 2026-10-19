// Screenshots for the README and docs, with a demo family and real fonts.
// Run: app/tool/screenshots.sh  (writes docs/screenshots/<lang>/*.png)
import 'dart:convert';
import 'dart:io';

import 'package:familienhub/core/theme/app_theme.dart';
import 'package:familienhub/l10n/l10n.dart';
import 'package:familienhub/models/themes.dart';
import 'package:familienhub/providers/providers.dart';
import 'package:familienhub/screens/main_shell.dart';
import 'package:familienhub/services/session_store.dart';
import 'package:familienhub/screens/more/appearance_screen.dart';
import 'package:familienhub/widgets/hub_background.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../test/helpers.dart';

String _d(DateTime d) => '${d.year}-${d.month.toString().padLeft(2, '0')}-${d.day.toString().padLeft(2, '0')}';

Future<void> _loadFonts() async {
  final root = Platform.environment['FLUTTER_ROOT'] ?? '';
  final material = '$root/bin/cache/artifacts/material_fonts';
  Future<void> load(String family, List<String> files) async {
    final loader = FontLoader(family);
    for (final f in files) {
      loader.addFont(Future.value(ByteData.sublistView(File(f).readAsBytesSync())));
    }
    await loader.load();
  }

  await load('Roboto', [for (final w in ['Regular', 'Medium', 'Bold']) '$material/Roboto-$w.ttf']);
  await load('MaterialIcons', ['$material/MaterialIcons-Regular.otf']);
  for (final family in ['PixelifySans', 'SpaceGrotesk', 'JetBrainsMono']) {
    await load(family, [for (final w in ['Regular', 'Bold']) 'assets/fonts/$family/$family-$w.ttf']);
  }
}

ThemeSpec _theme(String id) {
  final raw = jsonDecode(File('../backend/app/themes/$id.json').readAsStringSync()) as Map<String, dynamic>;
  return ThemeSpec.fromJson({'id': 'builtin:$id', 'builtin': true, ...raw});
}

/// Demo family "Example": nothing here is real household data.
FakeBackend _demo(String lang) {
  final de = lang == 'de';
  String t(String g, String e) => de ? g : e;
  final now = DateTime.now();
  final b = FakeBackend();
  addDefaults(b);
  b.json('GET', '/api/auth/me', {'id': 1, 'username': 'alex', 'display_name': 'Alex', 'role': 'admin', 'is_admin': true, 'avatar_color': '#E07A5F'});
  b.json('GET', '/api/auth/people', [
    {'id': 1, 'username': 'alex', 'display_name': 'Alex', 'avatar_color': '#E07A5F'},
    {'id': 2, 'username': 'sam', 'display_name': 'Sam', 'avatar_color': '#3D85C6'},
    {'id': 3, 'username': 'mia', 'display_name': 'Mia', 'avatar_color': '#81B29A'},
  ]);
  b.json('GET', '/api/modules', {
    'modules': {for (final m in ['today', 'reminders', 'meals', 'tasks', 'calendar', 'shopping', 'meal_planning']) m: {'enabled': true}},
    'plugins': [],
  });
  final tasks = [
    {'uid': 't1', 'title': t('Müll rausbringen', 'Take out the bins'), 'done': false, 'due': _d(now), 'assignee': 1,
     'list': {'name': t('Haushalt', 'Household'), 'kind': 'family'}},
    {'uid': 't2', 'title': t('Geschenk für Oma besorgen', 'Buy a present for Grandma'), 'done': false, 'due': _d(now.add(const Duration(days: 1))), 'assignee': 2, 'created_by': 1},
    {'uid': 't3', 'title': t('Hausaufgaben Mathe', 'Maths homework'), 'done': false, 'assignee': 3},
    {'uid': 't4', 'title': t('Fahrrad zur Werkstatt', 'Bike to the repair shop'), 'done': false, 'due': _d(now.add(const Duration(days: 3)))},
    {'uid': 't5', 'title': t('Pflanzen gießen', 'Water the plants'), 'done': false, 'list': {'name': t('Haushalt', 'Household'), 'kind': 'family'}},
    {'uid': 't6', 'title': t('Elternabend vorbereiten', 'Prepare for parents\' evening'), 'done': false, 'due': _d(now.add(const Duration(days: 1)))},
    {'uid': 't7', 'title': t('Schwimmsachen packen', 'Pack the swimming kit'), 'done': false, 'due': _d(now.add(const Duration(days: 2))), 'assignee': 3},
    {'uid': 't8', 'title': t('Altpapier entsorgen', 'Recycle old paper'), 'done': false, 'due': _d(now.add(const Duration(days: 5)))},
    {'uid': 't9', 'title': t('Zahnarzttermin ausmachen', 'Book a dentist appointment'), 'done': false},
  ];
  b.json('GET', '/api/today', {
    'date': _d(now),
    'events': [
      {'title': t('Kita-Sommerfest', 'Nursery summer party'), 'start': '${_d(now)}T15:00:00', 'end': '${_d(now)}T17:00:00'},
      {'title': t('Elternabend', 'Parents\' evening'), 'start': '${_d(now.add(const Duration(days: 1)))}T19:30:00'},
    ],
    'tasks': {'status': 'ok', 'error': null, 'items': tasks.take(3).toList()},
    'meals': [{'source': 'hub', 'title': t('Gemüselasagne', 'Vegetable lasagne')}],
    'shopping_open': 6,
    'reminders': [{'id': 1, 'title': t('Turnbeutel einpacken', 'Pack the gym bag'), 'due': '${_d(now)}T07:15:00'}],
    'notifications_unread': 2,
    'house': {'status': 'ok', 'error': null, 'items': [
      {'entity_id': 'sensor.washer', 'name': t('Waschmaschine', 'Washing machine'), 'state': t('fertig', 'done')},
      {'entity_id': 'sensor.living_temp', 'name': t('Wohnzimmer', 'Living room'), 'state': '21.5', 'unit': '°C'},
    ]},
  });
  b.json('GET', '/api/house/controls', {'status': 'ok', 'error': null, 'items': [
    {'entity_id': 'light.kitchen', 'name': t('Küche', 'Kitchen'), 'state': 'on', 'actions': ['turn_on', 'turn_off', 'brightness'], 'brightness': 180},
    {'entity_id': 'light.garden', 'name': t('Garten', 'Garden'), 'state': 'off', 'actions': ['turn_on', 'turn_off']},
  ]});
  b.json('GET', '/api/tasks', {'status': 'ok', 'error': null, 'items': tasks});
  final groceries = de
      ? ['Milch', 'Brot', 'Äpfel', 'Tomaten', 'Kaffee', 'Spülmittel']
      : ['Milk', 'Bread', 'Apples', 'Tomatoes', 'Coffee', 'Washing-up liquid'];
  b.json('GET', '/api/shopping', {'status': 'ok', 'error': null, 'groups': [
    {'key': 'manual', 'items': [for (var i = 0; i < groceries.length; i++) {'uid': 's$i', 'summary': groceries[i], 'status': 'needs_action'}]},
    {'key': 'recipes', 'items': [
      {'uid': 'r1', 'summary': t('Lasagneplatten', 'Lasagne sheets'), 'status': 'needs_action'},
      {'uid': 'r2', 'summary': t('Zucchini', 'Courgettes'), 'status': 'needs_action'},
    ]},
  ]});
  final monday = now.subtract(Duration(days: now.weekday - 1));
  final dishes = de
      ? ['Gemüselasagne', 'Linsensuppe', 'Pfannkuchen', 'Ofengemüse mit Feta', 'Pizza-Abend', 'Grillen', 'Sonntagsbraten']
      : ['Vegetable lasagne', 'Lentil soup', 'Pancakes', 'Roast vegetables with feta', 'Pizza night', 'Barbecue', 'Sunday roast'];
  b.on('GET', '/api/meals', (_) => jsonResponse({'status': 'ok', 'error': null, 'days': [
    for (var i = 0; i < 7; i++)
      {'date': _d(monday.add(Duration(days: i))), 'entries': [{'id': i + 1, 'title': dishes[i], 'source': 'hub', 'minutes': 20 + i * 5}]},
  ]}));
  b.json('GET', '/api/calendar/calendars', [
    {'id': 'hub', 'name': t('Familie', 'Family'), 'source': 'hub', 'writable': true, 'family': true},
    {'id': 'caldav:alex', 'name': 'Alex', 'source': 'caldav', 'color': '#E07A5F', 'writable': true},
    {'id': 'ics:ferien', 'name': t('Schulferien', 'School holidays'), 'source': 'ics', 'color': '#81B29A'},
    {'id': 'ics:muell', 'name': t('Müll', 'Bins'), 'source': 'ics', 'color': '#E3B23C'},
  ]);
  b.json('GET', '/api/calendar/events', [
    {'title': t('Kita-Sommerfest', 'Nursery summer party'), 'start': '${_d(now)}T15:00:00', 'end': '${_d(now)}T17:00:00', 'calendar_id': 'hub', 'calendar': t('Familie', 'Family')},
    {'title': t('Elternabend', 'Parents\' evening'), 'start': '${_d(now.add(const Duration(days: 1)))}T19:30:00', 'end': '${_d(now.add(const Duration(days: 1)))}T21:00:00', 'calendar_id': 'hub', 'calendar': t('Familie', 'Family')},
    {'title': t('Schwimmkurs Mia', 'Swimming lesson Mia'), 'start': '${_d(now.add(const Duration(days: 2)))}T16:00:00', 'end': '${_d(now.add(const Duration(days: 2)))}T17:00:00', 'calendar_id': 'hub', 'calendar': t('Familie', 'Family')},
    {'title': t('Zahnarzt', 'Dentist'), 'start': '${_d(now.add(const Duration(days: 3)))}T08:30:00', 'end': '${_d(now.add(const Duration(days: 3)))}T09:30:00', 'calendar_id': 'caldav:alex', 'calendar': 'Alex'},
    {'title': t('Oma Geburtstag', 'Grandma\'s birthday'), 'start': _d(now.add(const Duration(days: 4))), 'all_day': true, 'calendar_id': 'hub', 'calendar': t('Familie', 'Family')},
    {'title': t('Herbstferien', 'Autumn half-term'), 'start': _d(now.add(const Duration(days: 6))),
     'end': _d(now.add(const Duration(days: 13))), 'all_day': true, 'calendar': t('Schulferien', 'School holidays'), 'calendar_id': 'ics:ferien'},
    {'title': t('Gelbe Tonne', 'Recycling bin'), 'start': _d(now.add(const Duration(days: 1))), 'all_day': true, 'calendar_id': 'ics:muell', 'calendar': t('Müll', 'Bins')},
  ]);
  b.json('GET', '/api/reminders', []);
  b.json('GET', '/api/themes', {'items': [
    for (final id in ['warm', 'liquid-glass', 'clean-cards', 'neo-brutalism', 'pixel'])
      {'id': 'builtin:$id', 'builtin': true, ...jsonDecode(File('../backend/app/themes/$id.json').readAsStringSync()) as Map<String, dynamic>},
  ]});
  return b;
}

Widget _app(FakeBackend b, ThemeData theme, Widget home, {AppTab tab = AppTab.today}) => ProviderScope(
      overrides: [
        apiClientProvider.overrideWithValue(b.api(store: MemorySessionStore(url: 'https://hub.example.org', access: 'demo', refresh: 'demo'))),
        tabProvider.overrideWith((ref) => tab),
      ],
      child: MaterialApp(
        debugShowCheckedModeBanner: false,
        locale: Locale(appLanguage),
        supportedLocales: AppLocalizations.supportedLocales,
        localizationsDelegates: AppLocalizations.localizationsDelegates,
        theme: theme,
        builder: (context, child) => HubBackground(child: child ?? const SizedBox.shrink()),
        home: home,
      ),
    );

void main() {
  setUp(() async {
    await setUpTestEnv();
    await _loadFonts();
  });
  tearDown(() => setAppLanguage('de'));

  ThemeData light() => AppTheme.fromSpec(_theme('clean-cards').forBrightness(Brightness.light));
  ThemeData dark() => AppTheme.fromSpec(_theme('clean-cards').forBrightness(Brightness.dark));
  const shell = MainShell(startPush: false);
  final shots = <(String, ThemeData Function(), Widget, AppTab)>[
    ('today-light', light, shell, AppTab.today),
    ('today-dark', dark, shell, AppTab.today),
    ('calendar-light', light, shell, AppTab.calendar),
    ('calendar-dark', dark, shell, AppTab.calendar),
    ('tasks-light', light, shell, AppTab.tasks),
    ('tasks-dark', dark, shell, AppTab.tasks),
    ('shopping-light', light, shell, AppTab.shopping),
    ('shopping-dark', dark, shell, AppTab.shopping),
    ('settings-light', light, shell, AppTab.more),
    ('settings-dark', dark, shell, AppTab.more),
    // Showcase shots
    ('today-pixel', () => AppTheme.fromSpec(_theme('pixel').forBrightness(Brightness.light)), shell, AppTab.today),
    ('meals', () => AppTheme.fromSpec(_theme('liquid-glass').forBrightness(Brightness.dark)), shell, AppTab.meals),
    ('calendar-month', () => AppTheme.fromSpec(_theme('warm').forBrightness(Brightness.light)), shell, AppTab.calendar),
    ('themes', dark, const AppearanceScreen(), AppTab.more),
  ];

  for (final lang in ['en', 'de']) {
    for (final (name, theme, home, tab) in shots) {
      testWidgets('$lang/$name', (tester) async {
        // ignore: invalid_use_of_visible_for_testing_member
        if (name == 'calendar-month') SharedPreferences.setMockInitialValues({'calendar_view': 'month'});
        setAppLanguage(lang);
        tester.platformDispatcher.localeTestValue = Locale(lang);
        tester.view.physicalSize = const Size(1170, 2532); // phone, 390 × 844 at 3×
        tester.view.devicePixelRatio = 3;
        addTearDown(tester.view.reset);
        await tester.pumpWidget(_app(_demo(lang), theme(), home, tab: tab));
        await tester.pumpAndSettle(const Duration(milliseconds: 100), EnginePhase.sendSemanticsUpdate, const Duration(seconds: 5));
        await expectLater(find.byType(MaterialApp), matchesGoldenFile('../../docs/screenshots/$lang/$name.png'));
      });
    }
  }
}
