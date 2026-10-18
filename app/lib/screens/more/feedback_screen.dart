import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:url_launcher/url_launcher.dart';

import '../../providers/providers.dart';
import '../../services/app_info.dart';
import '../../widgets/common.dart';

const feedbackAreas = ['Heute', 'Aufgaben', 'Einkauf', 'Essen', 'Termine', 'Haus', 'Erinnerungen', 'Bücher',
  'Filme & Serien', 'Dokumente', 'Darstellung', 'Anmeldung', 'Anderes'];

/// Rückmeldung: an die Verwaltung der Familie (im Hub) oder an die Entwickler (GitHub-Issue, eigenes Konto).
class FeedbackScreen extends ConsumerStatefulWidget {
  /// Für Tests: statt Browser öffnen.
  final Future<bool> Function(Uri uri)? openUrl;
  const FeedbackScreen({super.key, this.openUrl});

  @override
  ConsumerState<FeedbackScreen> createState() => _FeedbackScreenState();
}

class _FeedbackScreenState extends ConsumerState<FeedbackScreen> {
  final _text = TextEditingController();
  String _area = 'Anderes';
  bool _busy = false;

  @override
  void dispose() {
    _text.dispose();
    super.dispose();
  }

  bool get _valid => _text.text.trim().length >= 3;

  Future<void> _toFamily() async {
    setState(() => _busy = true);
    final ok = await runAction(context, () => ref.read(apiClientProvider).sendFeedback(text: _text.text.trim(), area: _area));
    if (!mounted) return;
    setState(() => _busy = false);
    if (ok) {
      showInfo(context, 'Danke! Die Verwaltung hat deine Rückmeldung bekommen.');
      Navigator.pop(context);
    }
  }

  Future<void> _toGithub() async {
    final uri = githubIssueUri(text: _text.text, area: _area);
    final open = widget.openUrl ?? (u) => launchUrl(u, mode: LaunchMode.externalApplication);
    if (!await open(uri) && mounted) showInfo(context, 'Browser konnte nicht geöffnet werden');
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Scaffold(
      appBar: AppBar(title: const Text('Feedback senden')),
      body: ListView(padding: const EdgeInsets.all(16), children: [
        const Text('Was ist dir aufgefallen? Fehler, Wunsch oder Lob – je genauer, desto besser.'),
        const SizedBox(height: 12),
        DropdownButtonFormField<String>(
          key: const Key('feedback-area'),
          initialValue: _area,
          decoration: const InputDecoration(labelText: 'Bereich'),
          items: [for (final a in feedbackAreas) DropdownMenuItem(value: a, child: Text(a))],
          onChanged: (v) => setState(() => _area = v ?? 'Anderes'),
        ),
        const SizedBox(height: 12),
        TextField(
          key: const Key('feedback-text'),
          controller: _text,
          minLines: 4,
          maxLines: 10,
          maxLength: 4000,
          textCapitalization: TextCapitalization.sentences,
          decoration: const InputDecoration(labelText: 'Deine Rückmeldung', alignLabelWithHint: true),
          onChanged: (_) => setState(() {}),
        ),
        Text('Mitgeschickt werden App-Version ($appVersion) und Plattform ($appPlatform).',
            style: theme.textTheme.bodySmall),
        const SizedBox(height: 16),
        FilledButton.icon(
          key: const Key('feedback-family'),
          onPressed: _busy || !_valid ? null : _toFamily,
          icon: const Icon(Icons.family_restroom),
          label: const Text('An die Verwaltung der Familie'),
        ),
        const SizedBox(height: 8),
        OutlinedButton.icon(
          key: const Key('feedback-github'),
          onPressed: !_valid ? null : _toGithub,
          icon: const Icon(Icons.bug_report_outlined),
          label: const Text('An die Entwickler (GitHub)'),
        ),
        const SizedBox(height: 4),
        Text('Öffnet ein vorausgefülltes GitHub-Issue; abschicken mit deinem eigenen GitHub-Konto.',
            style: theme.textTheme.bodySmall),
      ]),
    );
  }
}
