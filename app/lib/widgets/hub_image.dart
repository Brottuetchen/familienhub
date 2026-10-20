import 'dart:typed_data';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../providers/providers.dart';

/// True for an address on the hub itself (`/api/plugins/photos/thumb/1`): it needs the login to load.
/// Absolute `http(s)` addresses (Mealie, Cookidoo) are loaded directly.
bool isHubImageUrl(String? url) => url != null && url.startsWith('/') && !url.startsWith('//');

/// An image from a URL that the server delivered. Hub-relative addresses (for example the image route of a plugin
/// that proxies a photo server) are fetched with the auth header, like profile pictures, and kept in memory;
/// absolute addresses load as usual. Without a URL, or if loading fails, [placeholder] is shown.
class HubImage extends StatelessWidget {
  final String? url;
  final double? width;
  final double? height;
  final BoxFit fit;
  final Widget placeholder;

  const HubImage({super.key, required this.url, required this.placeholder, this.width, this.height, this.fit = BoxFit.cover});

  @override
  Widget build(BuildContext context) {
    final u = url;
    if (u == null || u.isEmpty) return placeholder;
    if (isHubImageUrl(u)) return _AuthImage(url: u, width: width, height: height, fit: fit, placeholder: placeholder);
    return Image.network(u, width: width, height: height, fit: fit, errorBuilder: (_, __, ___) => placeholder);
  }
}

class _AuthImage extends ConsumerStatefulWidget {
  final String url;
  final double? width;
  final double? height;
  final BoxFit fit;
  final Widget placeholder;
  const _AuthImage({required this.url, required this.width, required this.height, required this.fit, required this.placeholder});

  @override
  ConsumerState<_AuthImage> createState() => _AuthImageState();
}

class _AuthImageState extends ConsumerState<_AuthImage> {
  late Future<Uint8List?> _bytes = ref.read(apiClientProvider).imageBytes(widget.url);

  @override
  void didUpdateWidget(_AuthImage old) {
    super.didUpdateWidget(old);
    if (old.url != widget.url) _bytes = ref.read(apiClientProvider).imageBytes(widget.url);
  }

  @override
  Widget build(BuildContext context) => FutureBuilder<Uint8List?>(
        future: _bytes,
        builder: (context, snap) {
          final data = snap.data;
          if (data == null) return widget.placeholder;
          return Image.memory(data,
              width: widget.width, height: widget.height, fit: widget.fit, gaplessPlayback: true,
              errorBuilder: (_, __, ___) => widget.placeholder);
        },
      );
}
