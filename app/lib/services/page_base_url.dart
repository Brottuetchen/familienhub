/// Server address of the web app, derived from the page's base URL (`document.baseURI`).
///
/// The backend writes `<base href>` with the sub-path it is served under (Home Assistant ingress), so the result
/// is e.g. `https://hub.example.org` at the root or `https://ha.local/api/hassio_ingress/<token>` below a prefix.
/// No trailing slash, because API paths are appended as `/api/...`.
String serverBaseFromPage(String baseUri) {
  final uri = Uri.parse(baseUri);
  var path = uri.path;
  while (path.endsWith('/')) {
    path = path.substring(0, path.length - 1);
  }
  return Uri(scheme: uri.scheme, host: uri.host, port: uri.hasPort ? uri.port : null, path: path).toString();
}
