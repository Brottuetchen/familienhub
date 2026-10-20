import 'dart:typed_data';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:url_launcher/url_launcher.dart';

import '../../l10n/l10n.dart';
import '../../models/plugin_card.dart';
import '../../providers/providers.dart';
import '../../widgets/common.dart';

/// A card an installed plugin adds to "Today": title, icon, a few lines, an optional picture and badge, and an
/// optional link that opens outside the app. The server has already validated and shortened all of it.
/// The picture is a hub path (`/api/plugins/<id>/…`) and is loaded with the login, like other hub images.
class PluginCard extends ConsumerWidget {
  final PluginCardData card;

  /// Opens the link; replaced in tests.
  final Future<void> Function(Uri uri)? openUrl;
  const PluginCard({super.key, required this.card, this.openUrl});

  Uri? get _link {
    final uri = Uri.tryParse(card.link ?? '');
    return uri != null && uri.scheme == 'https' && uri.host.isNotEmpty ? uri : null;
  }

  Future<void> _open(Uri uri) =>
      (openUrl ?? (u) => launchUrl(u, mode: LaunchMode.externalApplication))(uri);

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final theme = Theme.of(context);
    final muted = theme.textTheme.bodySmall?.copyWith(color: theme.colorScheme.onSurfaceVariant);
    final link = _link;
    final image = card.image;
    return SectionCard(
      key: Key('plugin-card-${card.key}'),
      icon: pluginCardIcon(card.icon),
      title: card.title,
      onTap: link == null ? null : () => _open(link),
      trailing: card.badge == null
          ? (link == null ? null : Icon(Icons.open_in_new, size: 18, color: theme.colorScheme.onSurfaceVariant))
          : ConstrainedBox(
              constraints: const BoxConstraints(maxWidth: 96),
              child: Container(
                key: Key('plugin-card-badge-${card.key}'),
                padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 2),
                decoration: BoxDecoration(
                  color: theme.colorScheme.primaryContainer,
                  borderRadius: BorderRadius.circular(12),
                ),
                child: Text(
                  card.badge!,
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style: theme.textTheme.labelSmall?.copyWith(color: theme.colorScheme.onPrimaryContainer),
                ),
              ),
            ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          if (image != null)
            Padding(
              padding: EdgeInsets.only(bottom: card.lines.isEmpty ? 0 : 8),
              child: _PluginCardImage(path: image, label: card.title),
            ),
          for (final line in card.lines)
            Padding(
              padding: const EdgeInsets.symmetric(vertical: 3),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(line.text),
                  if (line.secondary != null) Text(line.secondary!, style: muted),
                ],
              ),
            ),
          if (card.lines.isEmpty && image == null) Text(l10n.pluginCardEmpty, style: muted),
          if (link != null)
            Padding(
              padding: const EdgeInsets.only(top: 6),
              child: Text(l10n.pluginCardOpenLink(link.host), style: muted),
            ),
        ],
      ),
    );
  }
}

class _PluginCardImage extends ConsumerStatefulWidget {
  final String path;
  final String label;
  const _PluginCardImage({required this.path, required this.label});

  @override
  ConsumerState<_PluginCardImage> createState() => _PluginCardImageState();
}

class _PluginCardImageState extends ConsumerState<_PluginCardImage> {
  late Future<Uint8List?> _bytes = ref.read(apiClientProvider).pluginImageBytes(widget.path);

  @override
  void didUpdateWidget(_PluginCardImage old) {
    super.didUpdateWidget(old);
    if (old.path != widget.path) _bytes = ref.read(apiClientProvider).pluginImageBytes(widget.path);
  }

  @override
  Widget build(BuildContext context) {
    return FutureBuilder<Uint8List?>(
      future: _bytes,
      builder: (context, snap) {
        final bytes = snap.data;
        if (bytes == null) return const SizedBox.shrink(); // loading, offline or not an image: no picture
        return ClipRRect(
          borderRadius: BorderRadius.circular(8),
          child: ConstrainedBox(
            constraints: const BoxConstraints(maxHeight: 180),
            child: Image.memory(
              bytes,
              key: const Key('plugin-card-image'),
              width: double.infinity,
              fit: BoxFit.cover,
              gaplessPlayback: true,
              semanticLabel: widget.label,
              errorBuilder: (_, __, ___) => const SizedBox.shrink(),
            ),
          ),
        );
      },
    );
  }
}
