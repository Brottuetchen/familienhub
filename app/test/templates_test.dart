import 'package:familienhub/models/list_template.dart';
import 'package:familienhub/screens/shopping/shopping_screen.dart';
import 'package:familienhub/screens/tasks/tasks_screen.dart';
import 'package:familienhub/screens/templates/templates_screen.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'helpers.dart';

/// Reusable template lists (#20).
void main() {
  setUp(setUpTestEnv);

  FakeBackend backend({String role = 'partner'}) {
    final b = FakeBackend();
    addDefaults(b);
    b.json('GET', '/api/auth/me', {'id': 3, 'username': 'kim', 'role': role});
    b.json('GET', '/api/templates', {
      'items': [
        {
          'id': 7,
          'name': 'Packliste Wochenende mit sehr langem Namen',
          'item_count': 3,
          'items': [
            {'id': 70, 'name': 'Zahnbürste', 'note': ''},
            {'id': 71, 'name': 'Sonnencreme', 'note': 'LSF 50, die große Flasche'},
            {'id': 72, 'name': 'Ladekabel', 'note': ''},
          ],
        },
      ],
    });
    b.json('POST', '/api/templates/7/apply/shopping', {'status': 'ok', 'added': 1, 'skipped': 1, 'failed': 0});
    b.json('POST', '/api/templates/7/apply/tasks', {'status': 'ok', 'created': 2, 'failed': 0});
    b.json('POST', '/api/templates', {'id': 8, 'name': 'Neu', 'item_count': 1, 'items': []}, status: 201);
    b.json('POST', '/api/templates/from-shopping', {'id': 9, 'name': 'Woche', 'item_count': 1, 'items': []}, status: 201);
    return b;
  }

  Future<void> pump(WidgetTester tester, FakeBackend b, Widget screen, {double scale = 1}) async {
    const size = Size(360, 800);
    await setScreenSize(tester, size);
    tester.platformDispatcher.textScaleFactorTestValue = scale;
    addTearDown(tester.platformDispatcher.clearTextScaleFactorTestValue);
    await tester.pumpWidget(appWith(b.api(), screen));
    await tester.pumpAndSettle();
  }

  test('ListTemplate parses items and the apply result', () {
    final t = ListTemplate.fromJson({'id': 1, 'name': 'A', 'items': [{'id': 2, 'name': 'x'}]});
    expect(t.items.single.note, '');
    expect(TemplateApplied.fromJson({'created': 3}).added, 3);
  });

  testWidgets('apply a subset to the shopping list', (tester) async {
    final b = backend();
    await pump(tester, b, const TemplatesScreen(target: TemplateTarget.shopping));
    await tester.tap(find.byKey(const Key('template-7')));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const Key('template-item-72')));
    await tester.pump();
    await tester.tap(find.byKey(const Key('template-apply')));
    await tester.pumpAndSettle();
    final sent = b.sent('POST', '/api/templates/7/apply/shopping').single;
    expect(bodyOf(sent)['item_ids'], [70, 71]);
    expect(find.text('1 hinzugefügt, 1 standen schon auf der Liste'), findsOneWidget);
  });

  testWidgets('apply everything to the tasks on the family list', (tester) async {
    final b = backend();
    await pump(tester, b, const TemplatesScreen(target: TemplateTarget.tasks));
    await tester.tap(find.byKey(const Key('template-7')));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const Key('template-family')));
    await tester.pump();
    await tester.tap(find.byKey(const Key('template-apply')));
    await tester.pumpAndSettle();
    final body = bodyOf(b.sent('POST', '/api/templates/7/apply/tasks').single);
    expect(body['item_ids'], isNull);
    expect(body['list'], 'family');
  });

  testWidgets('children can apply but not edit', (tester) async {
    await pump(tester, backend(role: 'child'), const TemplatesScreen(target: TemplateTarget.shopping));
    expect(find.byKey(const Key('template-new')), findsNothing);
    expect(find.byKey(const Key('template-menu-7')), findsNothing);
    expect(find.byKey(const Key('template-7')), findsOneWidget);
  });

  testWidgets('create a template', (tester) async {
    final b = backend();
    await pump(tester, b, const TemplatesScreen(target: TemplateTarget.shopping));
    await tester.tap(find.byKey(const Key('template-new')));
    await tester.pumpAndSettle();
    await tester.enterText(find.byKey(const Key('template-name')), 'Neu');
    await tester.enterText(find.byKey(const Key('template-row-name-0')), 'Milch');
    await tester.enterText(find.byKey(const Key('template-row-note-0')), '2 l');
    await tester.tap(find.byKey(const Key('template-save')));
    await tester.pumpAndSettle();
    expect(bodyOf(b.sent('POST', '/api/templates').single), {
      'name': 'Neu',
      'items': [{'name': 'Milch', 'note': '2 l'}],
    });
  });

  testWidgets('shopping menu: open templates and save the list as a template', (tester) async {
    final b = backend();
    await pump(tester, b, const ShoppingScreen());
    await tester.tap(find.byKey(const Key('shopping-menu')));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Einkaufsliste als Vorlage speichern'));
    await tester.pumpAndSettle();
    await tester.enterText(find.byKey(const Key('template-name-dialog')), 'Woche');
    await tester.tap(find.text('Speichern'));
    await tester.pumpAndSettle();
    expect(bodyOf(b.sent('POST', '/api/templates/from-shopping').single), {'name': 'Woche'});
    await tester.tap(find.byKey(const Key('shopping-menu')));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Vorlagen'));
    await tester.pumpAndSettle();
    expect(find.byType(TemplatesScreen), findsOneWidget);
  });

  testWidgets('tasks menu opens the templates', (tester) async {
    await pump(tester, backend(), const TasksScreen());
    await tester.tap(find.byKey(const Key('tasks-menu')));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Vorlagen'));
    await tester.pumpAndSettle();
    expect(find.byType(TemplatesScreen), findsOneWidget);
  });

  for (final target in TemplateTarget.values) {
    testWidgets('no overflow at text scale 2.0 on 360 dp ($target)', (tester) async {
      final b = backend();
      await pump(tester, b, TemplatesScreen(target: target), scale: 2.0);
      expect(tester.takeException(), isNull);
      await tester.tap(find.byKey(const Key('template-7')));
      await tester.pumpAndSettle();
      expect(tester.takeException(), isNull);
      expect(find.byKey(const Key('template-apply')), findsOneWidget);
    });
  }

  testWidgets('no overflow in the editor at text scale 2.0 on 360 dp', (tester) async {
    await pump(
      tester,
      backend(),
      const TemplateEditScreen(
        template: ListTemplate(id: 7, name: 'Packliste Wochenende mit sehr langem Namen', items: [
          TemplateItem(id: 1, name: 'Sonnencreme', note: 'LSF 50, die große Flasche für alle'),
        ]),
      ),
      scale: 2.0,
    );
    expect(tester.takeException(), isNull);
  });
}
