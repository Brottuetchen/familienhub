import 'dart:typed_data';

import 'package:flutter/foundation.dart' show kIsWeb;
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:image_picker/image_picker.dart';

import '../../models/account.dart';
import '../../models/themes.dart' show hexColor;
import '../../providers/providers.dart';
import '../../widgets/common.dart';
import '../today/today_widgets.dart';
import 'avatar_crop_screen.dart';

/// Farben zur Auswahl für den eigenen Avatar (ohne Bild: zwei Buchstaben in dieser Farbe).
const avatarPalette = ['#8B5CF6', '#C2694A', '#2563EB', '#10B981', '#F59E0B', '#EC4899', '#22B8CF', '#64748B'];

/// Eigenes Profil: Bild, Anzeigename, Farbe. E-Mail und Anmeldung kommen aus Authentik.
class ProfileScreen extends ConsumerStatefulWidget {
  /// Für Tests: Bildauswahl ersetzen (sonst image_picker).
  final Future<Uint8List?> Function(ImageSource source)? pickImage;

  /// Für Tests: Zuschneiden ersetzen (sonst [AvatarCropScreen]).
  final Future<Uint8List?> Function(BuildContext context, Uint8List image)? cropImage;
  const ProfileScreen({super.key, this.pickImage, this.cropImage});

  @override
  ConsumerState<ProfileScreen> createState() => _ProfileScreenState();
}

class _ProfileScreenState extends ConsumerState<ProfileScreen> {
  late final TextEditingController _name;
  String? _color;
  bool _busy = false;

  @override
  void initState() {
    super.initState();
    final user = ref.read(sessionProvider).user;
    _name = TextEditingController(text: user?.profileName ?? user?.displayName ?? '');
    _color = user?.avatarColor;
  }

  @override
  void dispose() {
    _name.dispose();
    super.dispose();
  }

  Future<void> _apply(Future<AppUser> Function() action, {String? done}) async {
    setState(() => _busy = true);
    try {
      final user = await action();
      ref.read(sessionProvider.notifier).updateUser(user);
      ref.invalidate(peopleProvider);
      if (mounted && done != null) showInfo(context, done);
    } catch (e) {
      if (mounted) showError(context, e);
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<Uint8List?> _pick(ImageSource source) async {
    if (widget.pickImage != null) return widget.pickImage!(source);
    // Genug Auflösung zum Hineinzoomen; das Zuschneiden verkleinert danach auf 512 px
    final file = await ImagePicker().pickImage(source: source, maxWidth: 2048, maxHeight: 2048, imageQuality: 90);
    return file?.readAsBytes();
  }

  Future<Uint8List?> _crop(Uint8List image) {
    if (widget.cropImage != null) return widget.cropImage!(context, image);
    return Navigator.of(context).push<Uint8List>(
      MaterialPageRoute(fullscreenDialog: true, builder: (_) => AvatarCropScreen(image: image)),
    );
  }

  Future<void> _choosePhoto() async {
    final source = await showModalBottomSheet<ImageSource>(
      context: context,
      builder: (ctx) => SafeArea(
        child: Column(mainAxisSize: MainAxisSize.min, children: [
          if (!kIsWeb)
            ListTile(
              leading: const Icon(Icons.photo_camera_outlined),
              title: const Text('Foto aufnehmen'),
              onTap: () => Navigator.pop(ctx, ImageSource.camera),
            ),
          ListTile(
            leading: const Icon(Icons.photo_library_outlined),
            title: const Text('Aus der Galerie'),
            onTap: () => Navigator.pop(ctx, ImageSource.gallery),
          ),
        ]),
      ),
    );
    if (source == null || !mounted) return;
    final picked = await _pick(source);
    if (picked == null || !mounted) return;
    final bytes = await _crop(picked);
    if (bytes == null || !mounted) return;
    if (bytes.length > 512 * 1024) {
      showInfo(context, 'Das Bild ist zu groß (höchstens 512 KB).');
      return;
    }
    await _apply(() => ref.read(apiClientProvider).uploadAvatar(bytes), done: 'Profilbild gespeichert');
  }

  @override
  Widget build(BuildContext context) {
    final user = ref.watch(sessionProvider).user;
    final theme = Theme.of(context);
    if (user == null) return const Scaffold(body: Center(child: HubLoader()));
    final previewName = _name.text.trim().isEmpty ? (user.fullName ?? user.username) : _name.text.trim();
    return Scaffold(
      appBar: AppBar(title: const Text('Mein Profil')),
      body: ListView(
        padding: const EdgeInsets.fromLTRB(16, 16, 16, 32),
        children: [
          Center(
            child: Stack(
              children: [
                PersonAvatar(
                  key: const Key('profile-avatar'),
                  name: previewName,
                  id: user.id,
                  size: 112,
                  color: _color,
                  imageUrl: user.avatarUrl,
                ),
                Positioned(
                  right: 0,
                  bottom: 0,
                  child: IconButton.filled(
                    key: const Key('profile-photo'),
                    tooltip: 'Profilbild ändern',
                    onPressed: _busy ? null : _choosePhoto,
                    icon: const Icon(Icons.photo_camera_outlined),
                  ),
                ),
              ],
            ),
          ),
          if (user.avatarUrl != null)
            Center(
              child: TextButton.icon(
                key: const Key('profile-photo-remove'),
                onPressed: _busy ? null : () => _apply(() => ref.read(apiClientProvider).deleteAvatar(), done: 'Profilbild entfernt'),
                icon: const Icon(Icons.delete_outline),
                label: const Text('Bild entfernen'),
              ),
            ),
          const SizedBox(height: 20),
          TextField(
            key: const Key('profile-name'),
            controller: _name,
            maxLength: 40,
            textCapitalization: TextCapitalization.words,
            decoration: const InputDecoration(labelText: 'Anzeigename', helperText: 'So sieht dich die Familie im Hub'),
            onChanged: (_) => setState(() {}),
          ),
          const SizedBox(height: 16),
          Text('Farbe', style: theme.textTheme.titleSmall),
          const SizedBox(height: 8),
          Wrap(spacing: 10, runSpacing: 10, children: [
            for (final c in avatarPalette)
              InkWell(
                key: Key('profile-color-$c'),
                customBorder: const CircleBorder(),
                onTap: () => setState(() => _color = c),
                child: Container(
                  width: 40,
                  height: 40,
                  decoration: BoxDecoration(
                    color: hexColor(c),
                    shape: BoxShape.circle,
                    border: Border.all(color: theme.colorScheme.onSurface, width: _color == c ? 3 : 0),
                  ),
                  child: _color == c ? const Icon(Icons.check, color: Colors.white, size: 20) : null,
                ),
              ),
          ]),
          const SizedBox(height: 24),
          FilledButton(
            key: const Key('profile-save'),
            onPressed: _busy
                ? null
                : () => _apply(
                      () => ref.read(apiClientProvider).updateProfile(
                            displayName: _name.text.trim(),
                            avatarColor: _color,
                            clearColor: _color == null,
                          ),
                      done: 'Profil gespeichert',
                    ),
            child: _busy ? const HubLoader(size: 20) : const Text('Speichern'),
          ),
          const SizedBox(height: 24),
          ListTile(
            contentPadding: EdgeInsets.zero,
            leading: const Icon(Icons.alternate_email),
            title: const Text('Anmeldung'),
            subtitle: Text('${user.username} · über Authentik verwaltet'),
          ),
        ],
      ),
    );
  }
}
