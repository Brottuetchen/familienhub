import 'dart:async';

import 'package:familienhub/models/pending.dart';
import 'package:familienhub/services/api_client.dart';
import 'package:http/testing.dart';
import 'package:familienhub/models/task.dart';
import 'package:familienhub/screens/today/today_widgets.dart';
import 'package:familienhub/screens/shopping/shopping_screen.dart';
import 'package:familienhub/services/api_exceptions.dart';
import 'package:familienhub/services/offline_queue.dart';
import 'package:familienhub/services/session_store.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'helpers.dart';

PendingChange _c(String kind, {String? target, Map<String, dynamic>? body, String? conflict}) => PendingChange(
    id: PendingChange.newId(), kind: kind, method: 'POST', path: '/x', body: body, label: kind, target: target,
    created: DateTime(2026, 10, 17), conflict: conflict);

const _shopping = {
  'status': 'ok', 'error': null,
  'groups': [
    {'key': 'manual', 'items': [
      {'uid': 's1', 'summary': 'Milch', 'status': 'needs_action'},
      {'uid': 's2', 'summary': 'Brot', 'status': 'needs_action'},
    ]},
  ],
};

FakeBackend _backend() {
  final b = FakeBackend();
  addDefaults(b);
  b.json('GET', '/api/shopping', _shopping);
  b.json('POST', '/api/shopping', {'status': 'ok'});
  b.json('PATCH', '/api/shopping/s1', {'uid': 's1'});
  return b;
}

void main() {
  setUp(setUpTestEnv);

  group('Überlagerung', () {
    test('Einkauf: abhaken, löschen, hinzufügen; Konflikte nicht', () {
      final out = applyPending('shopping', _shopping, [
        _c('shopping_done', target: 's1', body: {'done': true}),
        _c('shopping_delete', target: 's2'),
        _c('shopping_add', body: {'item': 'Eier'}),
        _c('shopping_add', body: {'item': 'Abgelehnt'}, conflict: 'nein'),
      ]) as Map;
      final items = (out['groups'] as List).first['items'] as List;
      expect(items.map((i) => i['summary']), ['Milch', 'Eier']);
      expect(items.first['status'], 'completed');
      expect(items.first['pending'], isTrue);
      expect((items.last['uid'] as String).startsWith('pending:'), isTrue);
      expect((_shopping['groups'] as List).first['items'], hasLength(2), reason: 'Quelle bleibt unverändert');
    });

    test('Heute: erledigte Aufgabe und Zähler', () {
      final out = applyPending('today', {
        'tasks': {'status': 'ok', 'items': [{'uid': 't1', 'title': 'Müll', 'done': false}]},
        'shopping_open': 2,
      }, [
        _c('task_complete', target: 't1'),
        _c('shopping_add', body: {'item': 'Eier'}),
      ]) as Map;
      expect(((out['tasks'] as Map)['items'] as List).first['done'], isTrue);
      expect(out['shopping_open'], 3);
    });
  });

  group('Warteschlange', () {
    test('ohne Netz merken, mit Netz in Reihenfolge und mit gleichem Schlüssel senden', () async {
      final b = _backend()..offline = true;
      final store = MemorySessionStore(url: 'https://hub.test', access: 'token-1', refresh: 'refresh-1');
      final api = b.api(store: store);
      expect(await api.addShoppingItem('Eier'), isFalse);
      expect(await api.setShoppingDone('s1', true, name: 'Milch'), isFalse);
      final ids = api.pending.map((c) => c.id).toList();
      expect(api.pending.map((c) => c.label), ['„Eier“ auf die Einkaufsliste', '„Milch“ abgehakt']);

      // App neu gestartet: Warteschlange ist noch da
      final restarted = b.api(store: store);
      expect((await restarted.loadPending()).map((c) => c.id), ids);

      b.offline = false;
      await restarted.flushPending();
      expect(restarted.pending, isEmpty);
      final sent = b.requests.where((r) => r.method != 'GET').toList();
      expect(sent.map((r) => '${r.method} ${r.url.path}'), ['POST /api/shopping', 'PATCH /api/shopping/s1']);
      expect(sent.map((r) => r.headers['Idempotency-Key']), ids);
    });

    test('a new change does not wait for a slow queue ahead of it', () async {
      final b = _backend()..offline = true;
      final store = MemorySessionStore(url: 'https://hub.test', access: 'token-1', refresh: 'refresh-1');
      await b.api(store: store).addShoppingItem('Eins');
      final gate = Completer<void>();
      final api = ApiClient(
        httpClient: MockClient((request) async {
          if (request.method == 'POST') await gate.future; // slow server
          return b.routes['${request.method} ${request.url.path}']!(request);
        }),
        store: store,
      );
      final watch = Stopwatch()..start();
      final sent = await api.addShoppingItem('Zwei');
      expect(sent, isFalse, reason: 'queued behind the slow change, drains in the background');
      expect(watch.elapsed, lessThan(ApiClient.flushGrace + const Duration(seconds: 1)));
      expect(api.pending, hasLength(2));
      gate.complete();
      await api.flushPending();
      expect(api.pending, isEmpty);
    });

    test('Lesen zeigt gemerkte Änderungen sofort', () async {
      final b = _backend();
      final api = b.api();
      await api.shopping();
      b.offline = true;
      await api.addShoppingItem('Eier');
      final shown = (await api.cached('shopping', (j) => j))!.data as Map;
      final items = (shown['groups'] as List).first['items'] as List;
      expect(items.map((i) => i['summary']), contains('Eier'));
    });

    test('Ablehnung wird Konflikt, Serverausfall bleibt wartend, gelöschtes Löschen ist erledigt', () async {
      final b = _backend()..offline = true;
      final api = b.api();
      await api.setShoppingDone('weg', true, name: 'Butter');
      await api.addShoppingItem('Käse');
      await api.deleteShoppingItem('schon-weg', name: 'Salz');
      b.offline = false;
      b.json('PATCH', '/api/shopping/weg', {'detail': 'nicht gefunden'}, status: 404);
      b.json('POST', '/api/shopping', {'detail': 'HA weg'}, status: 503);
      await api.flushPending();
      expect(api.pending.first.conflict, contains('Gibt es nicht mehr'));
      expect(api.pending.map((c) => c.kind), ['shopping_done', 'shopping_add', 'shopping_delete'],
          reason: 'bei 503 wird abgebrochen und später erneut versucht');
      b.json('POST', '/api/shopping', {'status': 'ok'});
      b.json('DELETE', '/api/shopping/schon-weg', {'detail': 'nicht gefunden'}, status: 404);
      await api.flushPending();
      expect(api.pending.map((c) => c.kind), ['shopping_done'], reason: 'nur der Konflikt bleibt sichtbar');
      await api.discardPending(api.pending.single.id);
      expect(api.pending, isEmpty);
    });

    test('Serverwechsel verwirft gemerkte Änderungen', () async {
      final b = _backend()..offline = true;
      final api = b.api();
      await api.addShoppingItem('Eier');
      await api.setServer('https://anderer.test');
      expect(api.pending, isEmpty);
      expect(await api.loadPending(), isEmpty);
    });

    test('Haus und Essen werden nie gemerkt', () async {
      final b = _backend()..offline = true;
      final api = b.api();
      await expectLater(api.houseAction('light.lamp', 'turn_on'), throwsA(isA<OfflineException>()));
      await expectLater(api.addMeal(DateTime(2026, 10, 20), 'Suppe'), throwsA(isA<OfflineException>()));
      expect(api.pending, isEmpty);
    });
  });

  testWidgets('Einkauf offline: Artikel erscheint mit Wolke, Liste der wartenden Änderungen, später gesendet',
      (tester) async {
    await setScreenSize(tester, const Size(420, 1200));
    final b = _backend();
    final api = b.api();
    await tester.pumpWidget(appWith(api, const ShoppingScreen()));
    await tester.pumpAndSettle();
    b.offline = true;
    await tester.tap(find.widgetWithText(CheckboxListTile, 'Milch'));
    await tester.pumpAndSettle();
    expect(find.textContaining('Ohne Netz gemerkt'), findsOneWidget);
    await tester.tap(find.byTooltip('Erledigte zeigen')); // abgehakte Artikel sind sonst ausgeblendet
    await tester.pumpAndSettle();
    expect(find.byKey(const Key('pending-item-s1')), findsOneWidget);
    expect(tester.widget<CheckboxListTile>(find.widgetWithText(CheckboxListTile, 'Milch')).value, isTrue);
    expect(find.byKey(const Key('pending-changes')), findsOneWidget);

    await tester.tap(find.byKey(const Key('pending-changes')));
    await tester.pumpAndSettle();
    expect(find.text('„Milch“ abgehakt'), findsOneWidget);
    b.offline = false;
    await tester.tap(find.byKey(const Key('pending-send-now')));
    await tester.pumpAndSettle();
    expect(b.sent('PATCH', '/api/shopping/s1'), hasLength(1));
    expect(find.byKey(const Key('pending-changes')), findsNothing);
    expect(find.text('Alles gesendet'), findsOneWidget);
  });

  testWidgets('Heute offline: Nextcloud-Aufgabe abhaken wird gemerkt', (tester) async {
    await setScreenSize(tester, const Size(420, 800));
    final b = _backend()..offline = true;
    final api = b.api();
    await tester.pumpWidget(appWith(api, const Scaffold(body: TaskChecklist(online: false, tasks: [
      Task(uid: 't1', title: 'Müll rausbringen'),
    ]))));
    await tester.pumpAndSettle();
    final box = find.byType(Checkbox);
    expect(tester.widget<Checkbox>(box).onChanged, isNotNull, reason: 'auch offline bedienbar');
    await tester.tap(box);
    await tester.pumpAndSettle();
    expect(api.pending.single.label, '„Müll rausbringen“ erledigt');
    expect(find.textContaining('Ohne Netz gemerkt'), findsOneWidget);
    await api.discardPending(api.pending.single.id); // stoppt den Timer für den nächsten Sendeversuch
  });

  test('Aufgabe offline anlegen: erscheint vorläufig in der passenden Liste und auf Heute', () {
    final change = PendingChange(
        id: 'off-test-0001', kind: 'task_create', method: 'POST', path: '/api/tasks', body: {'title': 'Arzt anrufen'},
        label: 'x', created: DateTime(2026, 10, 17),
        meta: {'views': ['mine', 'today'], 'task': {'title': 'Arzt anrufen', 'done': false, 'due': '2026-10-17'}});
    final mine = applyPending('tasks:mine', {'status': 'ok', 'items': [{'uid': 't1', 'title': 'Alt'}]}, [change]) as Map;
    expect((mine['items'] as List).map((t) => t['uid']), ['pending:off-test-0001', 't1']);
    expect(Task.fromJson((mine['items'] as List).first as Map<String, dynamic>).localOnly, isTrue);
    final family = applyPending('tasks:family', {'status': 'ok', 'items': []}, [change]) as Map;
    expect(family['items'], isEmpty);
    final today = applyPending('today', {'tasks': {'status': 'ok', 'items': []}}, [change]) as Map;
    expect(((today['tasks'] as Map)['items'] as List).single['title'], 'Arzt anrufen');
  });

  test('Aufgabe offline anlegen und später genau einmal senden', () async {
    final b = _backend()..offline = true;
    b.json('POST', '/api/tasks', {'uid': 'neu1', 'title': 'Arzt anrufen'}, status: 201);
    final api = b.api();
    expect(await api.createTask(title: 'Arzt anrufen', due: DateTime.now(), meId: 1), isNull);
    final change = api.pending.single;
    expect(change.kind, 'task_create');
    expect(change.meta!['views'], ['mine', 'today']);
    expect(change.body, isNot(contains('views')), reason: 'Anzeige-Daten werden nicht gesendet');
    b.offline = false;
    await api.flushPending();
    expect(api.pending, isEmpty);
    final post = b.sent('POST', '/api/tasks').single;
    expect(post.headers['Idempotency-Key'], change.id);
    expect(bodyOf(post)['title'], 'Arzt anrufen');
  });

  test('Haushaltsrotation wird nicht offline gemerkt', () async {
    final b = _backend()..offline = true;
    final api = b.api();
    await expectLater(api.createTask(title: 'Bad putzen', rotation: [1, 2], recurrence: 'weekly'),
        throwsA(isA<OfflineException>()));
    expect(api.pending, isEmpty);
  });
}
