import '../l10n/l10n.dart';

/// Fehlerarten, die die Oberfläche unterscheiden muss.
class ApiException implements Exception {
  final int statusCode;
  final String message;
  ApiException(this.statusCode, this.message);

  @override
  String toString() => message;
}

/// 401 nach fehlgeschlagenem Refresh: Sitzung ist beendet.
class UnauthorizedException extends ApiException {
  UnauthorizedException() : super(401, l10n.pleaseSignInAgain);
}

/// 409 `no_write_access`: Liste gehört jemand anderem und ist nicht freigegeben.
class WriteAccessException extends ApiException {
  final String listName;
  WriteAccessException(this.listName)
      : super(409, l10n.listNotShared(listName));
}

/// 409 `no_caldav_account`: Nutzer hat noch kein Nextcloud-Konto hinterlegt.
class NoCalDavAccountException extends ApiException {
  NoCalDavAccountException()
      : super(409, l10n.nextcloudFirst);
}

/// Änderung ohne Netz. Lesen geht aus dem Cache, Schreiben nicht.
class OfflineException implements Exception {
  @override
  String toString() => l10n.noConnectionNotSaved;
}

/// Native mutation was accepted, but the authoritative read did not complete.
class NativeTaskConfirmedReadException extends ApiException {
  NativeTaskConfirmedReadException()
      : super(503, l10n.nativeStateStale);
}
