import 'package:expressive_loading_indicator/expressive_loading_indicator.dart';
import 'package:familienhub/models/common.dart';
import 'package:familienhub/widgets/common.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'helpers.dart';

// Das Status-Symbol zeigt auch wartende Offline-Änderungen und braucht dafür Riverpod (#32).
Widget _wrap(Widget child) => appWith(FakeBackend().api(), Scaffold(body: Center(child: child)));

void main() {
  setUp(setUpTestEnv);

  final at = DateTime(2026, 10, 17, 14, 32);

  for (final (name, result, icon, label) in [
    ('aktuell', ApiResult<int>(1, cachedAt: at), Icons.cloud_done_outlined, 'Aktuell, Stand 17.10. 14:32'),
    ('lädt', ApiResult<int>(1, cachedAt: at, refreshing: true), Icons.sync, 'Wird aktualisiert, Stand 17.10. 14:32'),
    ('offline', ApiResult<int>(1, cachedAt: at, offline: true), Icons.cloud_off, 'Offline, Stand 17.10. 14:32'),
    ('Fehler', ApiResult<int>(1, cachedAt: at, refreshError: StateError('Server weg')), Icons.sync_problem,
        'Aktualisierung fehlgeschlagen, Stand 17.10. 14:32'),
  ]) {
    testWidgets('Status-Symbol: $name', (tester) async {
      await tester.pumpWidget(_wrap(ReadStatusIcon(result: result)));
      expect(find.byIcon(icon), findsOneWidget);
      final tip = tester.widget<Tooltip>(find.byKey(const Key('read-status')));
      expect(tip.message, startsWith(label));
      expect(find.byType(Text), findsNothing); // nur ein Symbol, keine Textzeile
    });
  }

  testWidgets('Status-Symbol: Details beim Antippen', (tester) async {
    await tester.pumpWidget(_wrap(ReadStatusIcon(result: ApiResult<int>(1, cachedAt: at, offline: true))));
    await tester.tap(find.byKey(const Key('read-status')));
    await tester.pump(const Duration(milliseconds: 500));
    expect(find.text('Offline, Stand 17.10. 14:32'), findsOneWidget);
    await tester.pump(const Duration(seconds: 5));
  });

  testWidgets('Ladeanzeige: Formen statt drehendem Kreis, in Theme-Farbe', (tester) async {
    final theme = ThemeData(colorScheme: ColorScheme.fromSeed(seedColor: Colors.orange));
    await tester.pumpWidget(MaterialApp(theme: theme, home: const Scaffold(body: Center(child: HubLoader()))));
    await tester.pump(const Duration(milliseconds: 300));
    expect(find.byType(CircularProgressIndicator), findsNothing);
    final indicator = tester.widget<ExpressiveLoadingIndicator>(find.byType(ExpressiveLoadingIndicator));
    expect(indicator.color, theme.colorScheme.primary);
    expect(tester.getSize(find.byType(HubLoader)), const Size(48, 48));
    await tester.pumpWidget(const SizedBox.shrink()); // Animation beenden
  });
}
