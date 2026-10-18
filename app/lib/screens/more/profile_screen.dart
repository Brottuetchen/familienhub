import 'dart:typed_data';

import 'package:flutter/foundation.dart' show kIsWeb;
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:image_picker/image_picker.dart';

import '../../models/account.dart';
import '../../models/task.dart';
import '../../models/themes.dart' show hexColor;
import '../../providers/providers.dart';
import '../../widgets/common.dart';
import '../today/today_widgets.dart';
import 'avatar_crop_screen.dart';
import '../../l10n/l10n.dart';

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
              title: Text(l10n.takePhoto),
              onTap: () => Navigator.pop(ctx, ImageSource.camera),
            ),
          ListTile(
            leading: const Icon(Icons.photo_library_outlined),
            title: Text(l10n.fromGallery),
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
      showInfo(context, l10n.imageTooLarge);
      return;
    }
    await _apply(() => ref.read(apiClientProvider).uploadAvatar(bytes), done: l10n.avatarSaved);
  }

  Future<void> _setPlace(String? place) async {
    setState(() => _busy = true);
    try {
      await ref.read(apiClientProvider).setTaskPlace(place);
      ref.invalidate(taskPlaceProvider);
      if (mounted) showInfo(context, l10n.taskPlaceSaved);
    } catch (e) {
      if (mounted) showError(context, e);
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  /// Where tasks that others give me land: automatic (derived from the connected accounts) or a chosen place.
  /// Hidden while the server does not answer (older server, offline).
  Widget _taskPlaceSection(ThemeData theme) {
    final info = ref.watch(taskPlaceProvider).valueOrNull;
    if (info == null) return const SizedBox.shrink();
    final selected = info.explicit != null && info.options.any((o) => o.id == info.explicit && o.available) ? info.explicit : null;
    return Padding(
      key: const Key('task-place-section'),
      padding: const EdgeInsets.only(bottom: 16),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Text(l10n.taskPlace, style: theme.textTheme.titleSmall),
        const SizedBox(height: 4),
        Text(l10n.taskPlaceHint, style: theme.textTheme.bodySmall),
        RadioGroup<String>(
          groupValue: selected ?? '',
          onChanged: (value) { if (!_busy) _setPlace(value == null || value.isEmpty ? null : value); },
          child: Column(children: [
            RadioListTile<String>(
              key: const Key('task-place-auto'),
              contentPadding: EdgeInsets.zero,
              value: '',
              title: Text(l10n.taskPlaceAuto(info.auto == null ? '' : taskPlaceName(info.auto!))),
            ),
            for (final option in info.options)
              RadioListTile<String>(
                key: Key('task-place-${option.id}'),
                contentPadding: EdgeInsets.zero,
                value: option.id,
                enabled: option.available,
                title: Text(taskPlaceName(option.id)),
              ),
          ]),
        ),
      ]),
    );
  }

  @override
  Widget build(BuildContext context) {
    final user = ref.watch(sessionProvider).user;
    final theme = Theme.of(context);
    if (user == null) return const Scaffold(body: Center(child: HubLoader()));
    final previewName = _name.text.trim().isEmpty ? (user.fullName ?? user.username) : _name.text.trim();
    return Scaffold(
      appBar: AppBar(title: Text(l10n.myProfile)),
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
                    tooltip: l10n.changeAvatar,
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
                onPressed: _busy ? null : () => _apply(() => ref.read(apiClientProvider).deleteAvatar(), done: l10n.avatarRemoved),
                icon: const Icon(Icons.delete_outline),
                label: Text(l10n.removeImage),
              ),
            ),
          const SizedBox(height: 20),
          TextField(
            key: const Key('profile-name'),
            controller: _name,
            maxLength: 40,
            textCapitalization: TextCapitalization.words,
            decoration: InputDecoration(labelText: l10n.displayName, helperText: l10n.displayNameHint),
            onChanged: (_) => setState(() {}),
          ),
          const SizedBox(height: 16),
          Text(l10n.colour, style: theme.textTheme.titleSmall),
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
                      done: l10n.profileSaved,
                    ),
            child: _busy ? const HubLoader(size: 20) : Text(l10n.save),
          ),
          const SizedBox(height: 24),
          _taskPlaceSection(theme),
          ListTile(
            contentPadding: EdgeInsets.zero,
            leading: const Icon(Icons.alternate_email),
            title: Text(l10n.signIn),
            subtitle: Text(l10n.managedByAuthentik(user.username)),
          ),
        ],
      ),
    );
  }
}
