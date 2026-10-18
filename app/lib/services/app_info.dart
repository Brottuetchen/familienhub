import 'package:flutter/foundation.dart' show TargetPlatform, defaultTargetPlatform, kIsWeb;

/// Version vom Release-Build (`--dart-define=FH_VERSION=1.0.0+420`), sonst „dev“.
const appVersion = String.fromEnvironment('FH_VERSION', defaultValue: 'dev');

/// Projekt auf GitHub: Rückmeldungen an die Entwickler landen dort als Issue (vorausgefüllt, eigenes Konto).
const projectIssuesUrl = 'https://github.com/Brottuetchen/familienhub/issues/new';

String get appPlatform => kIsWeb
    ? 'web'
    : switch (defaultTargetPlatform) {
        TargetPlatform.android => 'android',
        TargetPlatform.iOS => 'ios',
        _ => 'other',
      };

/// Vorausgefülltes GitHub-Issue. Enthält nur, was die Person selbst schreibt, plus Version/Plattform/Bereich –
/// keine Server-Adresse, keine Namen.
Uri githubIssueUri({required String text, String? area}) {
  final firstLine = text.trim().split('\n').first;
  final title = firstLine.length > 70 ? '${firstLine.substring(0, 70)}…' : firstLine;
  final body = [
    text.trim(),
    '',
    '---',
    '- App-Version: $appVersion',
    '- Plattform: $appPlatform',
    if (area != null && area.isNotEmpty) '- Bereich: $area',
  ].join('\n');
  return Uri.parse(projectIssuesUrl).replace(queryParameters: {'title': title, 'body': body, 'labels': 'feedback'});
}
