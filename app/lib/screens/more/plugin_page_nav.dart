/// Pure helpers for the in-app plugin page: which addresses the WebView may show and how a fresh link keeps the
/// sub-path the person was on.
library;

/// The `/plugin-pages/<token>/` prefix of a signed link, or null when [link] is not one.
String? pluginPageTokenPrefix(Uri link) {
  final segs = link.pathSegments;
  if (segs.length < 2 || segs.first != 'plugin-pages' || segs[1].isEmpty) return null;
  return '/plugin-pages/${segs[1]}/';
}

bool _sameOrigin(Uri a, Uri b) =>
    a.scheme == b.scheme && a.host.toLowerCase() == b.host.toLowerCase() && _port(a) == _port(b);

int _port(Uri u) => u.hasPort ? u.port : (u.scheme == 'https' ? 443 : 80);

/// True when the WebView may navigate to [target]: the hub's origin and the signed prefix of this very link.
/// Everything else (other servers, other paths of the hub such as `/api`, `mailto:`) goes to the system.
bool isPluginPageNavigationAllowed(Uri target, {required Uri hub, required Uri link}) {
  final prefix = pluginPageTokenPrefix(link);
  if (prefix == null) return false;
  if (!_sameOrigin(target, hub) || !_sameOrigin(target, link)) return false;
  return target.path.startsWith(prefix);
}

/// The path below the token prefix (`2026-10/index.html`) of [current], '' for the page itself. It is what the hub's
/// link endpoint takes as `path`, so a refreshed link lands on the same sub-page.
String pluginPageSubPath(Uri current, Uri link) {
  final prefix = pluginPageTokenPrefix(link);
  if (prefix == null || !current.path.startsWith(prefix)) return '';
  return current.path.substring(prefix.length);
}

/// HTTP statuses of the main frame that mean "the signed link is no longer good".
bool isExpiredLinkStatus(int? status) => status == 401 || status == 403 || status == 404 || status == 410;
