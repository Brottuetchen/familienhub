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
  UnauthorizedException() : super(401, 'Bitte erneut anmelden');
}

/// 409 `no_write_access`: Liste gehört jemand anderem und ist nicht freigegeben.
class WriteAccessException extends ApiException {
  final String listName;
  WriteAccessException(this.listName)
      : super(409, 'Die Liste „$listName“ ist nicht für dich freigegeben');
}

/// 409 `no_caldav_account`: Nutzer hat noch kein Nextcloud-Konto hinterlegt.
class NoCalDavAccountException extends ApiException {
  NoCalDavAccountException()
      : super(409, 'Bitte zuerst unter Mehr → Nextcloud-Konto dein Konto eintragen');
}

/// Änderung ohne Netz. Lesen geht aus dem Cache, Schreiben nicht.
class OfflineException implements Exception {
  @override
  String toString() => 'Keine Verbindung zum Server – Änderung nicht gespeichert';
}

/// Native mutation was accepted, but the authoritative read did not complete.
class NativeTaskConfirmedReadException extends ApiException {
  NativeTaskConfirmedReadException()
      : super(503, 'Änderung bestätigt, aber der native Zustand konnte nicht aktualisiert werden. Bitte neu laden; nicht wiederholen.');
}
