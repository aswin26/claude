import os, time, json, requests
from requests_toolbelt import MultipartEncoder
import config


class AppianClient:
    def __init__(self, base_url, api_key):
        self.base_url    = base_url.rstrip("/")
        self.base_deploy = f"{self.base_url}/suite/deployment-management/v2"
        self.session     = requests.Session()
        self.session.headers.update({"appian-api-key": api_key})
        if config.PROXIES:
            self.session.proxies.update(config.PROXIES)

    # ── Applications ──────────────────────────────────────────────

    def list_applications(self):
        return self._get(f"{self.base_url}/suite/api/v2/applications").json()

    # ── Export ────────────────────────────────────────────────────

    def export_package(self, app_uuid: str) -> bytes:
        """Trigger export, poll until complete, return zip bytes."""
        url = f"{self.base_deploy}/deployments"
        payload = {
            "exportType":  "application",
            "uuids":       [app_uuid],
            "name":        f"Export-{app_uuid[:8]}",
            "description": "Exported via appian_workflow.py",
        }
        multipart = MultipartEncoder(fields={
            "json": (None, json.dumps(payload), "application/json"),
        })
        resp = self._post(
            url,
            headers={"Action-Type": "export", "Content-Type": multipart.content_type},
            data=multipart,
        )
        result       = resp.json()
        deploy_uuid  = result.get("uuid")
        print(f"  Export triggered — deployment UUID: {deploy_uuid}")

        result = self._poll_status(
            f"{self.base_deploy}/deployments/{deploy_uuid}",
            {"COMPLETED", "COMPLETED_WITH_ERRORS", "FAILED"},
        )
        if result.get("status") == "FAILED":
            raise RuntimeError(f"Export failed: {json.dumps(result)}")

        # Get download URL from completed deployment
        meta         = self._get(f"{self.base_deploy}/deployments/{deploy_uuid}").json()
        download_url = meta.get("packageZip") or meta.get("url")
        if not download_url:
            raise RuntimeError(f"No download URL in export response: {json.dumps(meta)}")

        with self.session.get(download_url, stream=True, timeout=120) as r:
            r.raise_for_status()
            return r.content

    # ── Inspect ───────────────────────────────────────────────────

    def inspect_package(self, zip_path: str) -> dict:
        """Inspect a .zip package file. Returns inspection result dict."""
        url          = f"{self.base_deploy}/inspections"
        package_name = os.path.basename(zip_path)
        payload      = {"packageFileName": package_name}

        with open(zip_path, "rb") as zf:
            multipart = MultipartEncoder(fields={
                "json":    json.dumps(payload),
                "package": (package_name, zf, "application/zip"),
            })
            resp = self._post(
                url,
                headers={"Content-Type": multipart.content_type},
                data=multipart,
            )

        result = resp.json()
        uuid   = result.get("uuid")
        if uuid:
            result = self._poll_status(
                f"{url}/{uuid}",
                {"COMPLETED", "COMPLETED_WITH_ERRORS", "FAILED"},
            )
        return result

    # ── Deploy ────────────────────────────────────────────────────

    def deploy_package(self, zip_path: str, name="Automated Deployment", description="") -> dict:
        """Deploy a .zip package file. Returns deployment result dict."""
        url          = f"{self.base_deploy}/deployments"
        package_name = os.path.basename(zip_path)
        payload      = {
            "name":            name,
            "description":     description,
            "packageFileName": package_name,
        }

        with open(zip_path, "rb") as zf:
            multipart = MultipartEncoder(fields={
                "json":    json.dumps(payload),
                "package": (package_name, zf, "application/zip"),
            })
            resp = self._post(
                url,
                headers={"Action-Type": "import", "Content-Type": multipart.content_type},
                data=multipart,
            )

        result = resp.json()
        uuid   = result.get("uuid")
        if uuid:
            result = self._poll_status(
                f"{url}/{uuid}",
                {"COMPLETED", "COMPLETED_WITH_ERRORS", "FAILED"},
            )
        return result

    # ── Internal helpers ──────────────────────────────────────────

    def _get(self, url, **kw):
        kw.setdefault("timeout", config.REQUEST_TIMEOUT)
        r = self.session.get(url, **kw)
        r.raise_for_status()
        return r

    def _post(self, url, **kw):
        kw.setdefault("timeout", config.REQUEST_TIMEOUT)
        r = self.session.post(url, **kw)
        r.raise_for_status()
        return r

    def _poll_status(self, url, terminal):
        deadline = time.time() + config.DEPLOY_POLL_TIMEOUT
        while time.time() < deadline:
            body   = self._get(url).json()
            status = body.get("status", "UNKNOWN")
            print(f"  ... status: {status}")
            if status in terminal:
                return body
            time.sleep(config.DEPLOY_POLL_INTERVAL)
        raise TimeoutError(f"Timed out after {config.DEPLOY_POLL_TIMEOUT}s")
