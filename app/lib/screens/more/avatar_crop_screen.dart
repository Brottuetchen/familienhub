import 'package:crop_your_image/crop_your_image.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:image/image.dart' as img;

import '../../widgets/common.dart';
import '../../l10n/l10n.dart';

/// Kantenlänge des gespeicherten Profilbilds.
const avatarPixels = 512;

/// Zugeschnittenes Bild für den Upload: quadratisch, höchstens [avatarPixels] groß, JPEG.
/// Wirft [FormatException], wenn sich das Bild nicht lesen lässt.
Uint8List prepareAvatar(Uint8List bytes) {
  final decoded = img.decodeImage(bytes);
  if (decoded == null) throw FormatException(l10n.imageUnreadable);
  var out = img.bakeOrientation(decoded);
  final side = out.width < out.height ? out.width : out.height;
  if (out.width != out.height) {
    out = img.copyCrop(out, x: (out.width - side) ~/ 2, y: (out.height - side) ~/ 2, width: side, height: side);
  }
  if (side > avatarPixels) out = img.copyResize(out, width: avatarPixels, height: avatarPixels, interpolation: img.Interpolation.average);
  return Uint8List.fromList(img.encodeJpg(out, quality: 85));
}

Uint8List _rotate(Uint8List bytes) {
  final decoded = img.decodeImage(bytes);
  if (decoded == null) return bytes;
  return Uint8List.fromList(img.encodeJpg(img.copyRotate(img.bakeOrientation(decoded), angle: 90), quality: 95));
}

/// Profilbild zuschneiden: im Kreis verschieben, zoomen, drehen. Gibt die fertigen JPEG-Bytes zurück.
class AvatarCropScreen extends StatefulWidget {
  final Uint8List image;
  const AvatarCropScreen({super.key, required this.image});

  @override
  State<AvatarCropScreen> createState() => _AvatarCropScreenState();
}

class _AvatarCropScreenState extends State<AvatarCropScreen> {
  final _controller = CropController();
  late Uint8List _image = widget.image;
  bool _ready = false;
  bool _busy = false;

  Future<void> _rotateImage() async {
    setState(() {
      _busy = true;
      _ready = false;
    });
    final rotated = await compute(_rotate, _image);
    if (!mounted) return;
    setState(() {
      _image = rotated;
      _busy = false;
    });
    _controller.image = rotated;
  }

  Future<void> _onCropped(CropResult result) async {
    switch (result) {
      case CropSuccess(:final croppedImage):
        try {
          final out = await compute(prepareAvatar, croppedImage);
          if (mounted) Navigator.pop(context, out);
        } catch (e) {
          if (mounted) {
            setState(() => _busy = false);
            showError(context, e);
          }
        }
      case CropFailure(:final cause):
        if (mounted) {
          setState(() => _busy = false);
          showError(context, cause);
        }
    }
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Scaffold(
      backgroundColor: Colors.black,
      appBar: AppBar(
        backgroundColor: Colors.black,
        foregroundColor: Colors.white,
        title: Text(l10n.cropImage),
        actions: [
          IconButton(
            key: const Key('crop-rotate'),
            tooltip: l10n.rotate,
            onPressed: _busy || !_ready ? null : _rotateImage,
            icon: const Icon(Icons.rotate_90_degrees_cw_outlined),
          ),
        ],
      ),
      body: SafeArea(
        child: Column(children: [
          Expanded(
            child: Crop(
              image: _image,
              controller: _controller,
              aspectRatio: 1,
              withCircleUi: true,
              interactive: true, // Bild mit zwei Fingern zoomen und verschieben
              fixCropRect: true,
              initialRectBuilder: InitialRectBuilder.withSizeAndRatio(size: 0.85, aspectRatio: 1),
              baseColor: Colors.black,
              maskColor: Colors.black.withValues(alpha: 0.6),
              progressIndicator: const Center(child: HubLoader()),
              onStatusChanged: (s) {
                if (mounted) setState(() => _ready = s == CropStatus.ready);
              },
              onCropped: _onCropped,
            ),
          ),
          Padding(
            padding: const EdgeInsets.fromLTRB(16, 12, 16, 16),
            child: Column(children: [
              Text(l10n.cropHint,
                  style: theme.textTheme.bodySmall?.copyWith(color: Colors.white70)),
              const SizedBox(height: 12),
              Row(children: [
                Expanded(
                  child: OutlinedButton(
                    style: OutlinedButton.styleFrom(foregroundColor: Colors.white),
                    onPressed: _busy ? null : () => Navigator.pop(context),
                    child: Text(l10n.cancel),
                  ),
                ),
                const SizedBox(width: 12),
                Expanded(
                  child: FilledButton(
                    key: const Key('crop-done'),
                    onPressed: _busy || !_ready
                        ? null
                        : () {
                            setState(() => _busy = true);
                            _controller.crop();
                          },
                    child: _busy ? const HubLoader(size: 20) : Text(l10n.apply),
                  ),
                ),
              ]),
            ]),
          ),
        ]),
      ),
    );
  }
}
