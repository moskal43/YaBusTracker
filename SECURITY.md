# Security

Report suspected vulnerabilities through the repository's **Security → Report a
vulnerability** feature. Do not put credentials, cookies, signed URLs, private
Home Assistant addresses, or full configuration files in public issues.

YaBusTracker uses a fixed HTTPS Yandex Maps endpoint. Stop links are parsed
locally and are not used as arbitrary request destinations. Session cookies and
CSRF tokens are held only in memory. Requests have time/size limits, reject
redirects and non-JSON responses, and use shared backoff after errors.

The underlying API is undocumented and can change. Please use the latest release;
availability of the upstream service and a response-time SLA are not guaranteed.
