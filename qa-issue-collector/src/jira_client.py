import base64
import json
import mimetypes
import uuid
from dataclasses import dataclass
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


class JiraError(RuntimeError):
    pass


@dataclass(frozen=True)
class JiraProject:
    id: str
    key: str
    name: str

    @property
    def display_name(self):
        return f"{self.key} - {self.name}"


@dataclass(frozen=True)
class JiraIssueType:
    id: str
    name: str
    description: str = ""


@dataclass(frozen=True)
class JiraField:
    key: str
    name: str
    required: bool
    field_type: str
    allowed_values: tuple[str, ...] = ()


@dataclass(frozen=True)
class JiraUser:
    account_id: str
    name: str
    display_name: str
    email: str = ""

    @property
    def display_label(self):
        identity = self.email or self.name or self.account_id
        if identity and identity != self.display_name:
            return f"{self.display_name} ({identity})"
        return self.display_name or identity


@dataclass(frozen=True)
class JiraComponent:
    id: str
    name: str


class JiraClient:
    def __init__(self, project_root):
        self.project_root = Path(project_root)
        self.config_path = self.project_root / "config" / "settings.json"
        self.base_url = ""
        self.email = ""
        self.api_token = ""
        self.load_settings()

    def load_settings(self):
        data = self.read_config().get("jira", {})
        self.base_url = data.get("url", "")
        self.email = data.get("email", "")
        self.api_token = data.get("api_token", "")

    def save_settings(self, base_url, email, api_token):
        data = self.read_config()
        data["jira"] = {
            "url": base_url.rstrip("/"),
            "email": email,
            "api_token": api_token,
        }
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        with self.config_path.open("w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        self.base_url = data["jira"]["url"]
        self.email = email
        self.api_token = api_token

    def read_config(self):
        if not self.config_path.exists():
            return {}
        try:
            with self.config_path.open("r", encoding="utf-8") as f:
                return json.load(f)
        except (OSError, json.JSONDecodeError):
            return {}

    def is_configured(self):
        return bool(self.base_url and self.email and self.api_token)

    def request_json(self, method, path, params=None, body=None, extra_headers=None):
        if not self.is_configured():
            raise JiraError("Jira URL, 계정, API Token을 먼저 저장해주세요.")

        url = f"{self.base_url}{path}"
        if params:
            url = f"{url}?{urlencode(params)}"

        auth = base64.b64encode(f"{self.email}:{self.api_token}".encode("utf-8")).decode("ascii")
        request = Request(
            url,
            method=method,
            headers={
                "Authorization": f"Basic {auth}",
                "Accept": "application/json",
                "Content-Type": "application/json",
                **(extra_headers or {}),
            },
            data=json.dumps(body).encode("utf-8") if body is not None else None,
        )

        try:
            with urlopen(request, timeout=30) as response:
                body = response.read().decode("utf-8")
        except HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise JiraError(f"Jira API 오류 {exc.code}: {detail or exc.reason}") from exc
        except URLError as exc:
            raise JiraError(f"Jira 연결 실패: {exc.reason}") from exc

        if not body.strip():
            return {}
        return json.loads(body)

    def request_raw(self, method, path, body, content_type, extra_headers=None):
        if not self.is_configured():
            raise JiraError("Jira URL, 계정, API Token을 먼저 저장해주세요.")

        auth = base64.b64encode(f"{self.email}:{self.api_token}".encode("utf-8")).decode("ascii")
        request = Request(
            f"{self.base_url}{path}",
            method=method,
            headers={
                "Authorization": f"Basic {auth}",
                "Accept": "application/json",
                "Content-Type": content_type,
                **(extra_headers or {}),
            },
            data=body,
        )

        try:
            with urlopen(request, timeout=120) as response:
                response_body = response.read().decode("utf-8")
        except HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise JiraError(f"Jira API 오류 {exc.code}: {detail or exc.reason}") from exc
        except URLError as exc:
            raise JiraError(f"Jira 연결 실패: {exc.reason}") from exc

        if not response_body.strip():
            return {}
        return json.loads(response_body)

    def get_myself(self):
        try:
            return self.request_json("GET", "/rest/api/3/myself")
        except JiraError:
            return self.request_json("GET", "/rest/api/2/myself")

    def list_projects(self):
        try:
            data = self.request_json("GET", "/rest/api/3/project/search", {"maxResults": 100})
            items = data.get("values", [])
        except JiraError:
            items = self.request_json("GET", "/rest/api/2/project")

        projects = []
        for item in items:
            projects.append(
                JiraProject(
                    id=str(item.get("id", "")),
                    key=item.get("key", ""),
                    name=item.get("name", ""),
                )
            )
        return sorted(projects, key=lambda project: project.display_name.lower())

    def list_issue_types(self, project):
        project_id = project.id
        project_key = project.key

        if project_id:
            try:
                data = self.request_json("GET", "/rest/api/3/issuetype/project", {"projectId": project_id})
                return self.parse_issue_types(data)
            except JiraError:
                pass

        for path in (f"/rest/api/3/project/{project_key}", f"/rest/api/2/project/{project_key}"):
            try:
                data = self.request_json("GET", path)
                issue_types = data.get("issueTypes", [])
                if issue_types:
                    return self.parse_issue_types(issue_types)
            except JiraError:
                continue

        raise JiraError("해당 프로젝트의 이슈 타입 목록을 가져오지 못했습니다.")

    def parse_issue_types(self, items):
        issue_types = []
        for item in items:
            issue_types.append(
                JiraIssueType(
                    id=str(item.get("id", "")),
                    name=item.get("name", ""),
                    description=item.get("description", ""),
                )
            )
        return sorted(issue_types, key=lambda issue_type: issue_type.name.lower())

    def list_create_fields(self, project, issue_type):
        try:
            data = self.request_json(
                "GET",
                f"/rest/api/3/issue/createmeta/{project.key}/issuetypes/{issue_type.id}",
            )
            fields = data.get("fields", [])
            return self.parse_fields(fields)
        except JiraError:
            pass

        try:
            data = self.request_json(
                "GET",
                "/rest/api/3/issue/createmeta",
                {
                    "projectKeys": project.key,
                    "issuetypeIds": issue_type.id,
                    "expand": "projects.issuetypes.fields",
                },
            )
            return self.parse_legacy_createmeta_fields(data, project.key, issue_type.id)
        except JiraError:
            pass

        data = self.request_json(
            "GET",
            "/rest/api/2/issue/createmeta",
            {
                "projectKeys": project.key,
                "issuetypeIds": issue_type.id,
                "expand": "projects.issuetypes.fields",
            },
        )
        return self.parse_legacy_createmeta_fields(data, project.key, issue_type.id)

    def parse_fields(self, items):
        fields = []
        for item in items:
            fields.append(
                JiraField(
                    key=item.get("fieldId", item.get("key", "")),
                    name=item.get("name", ""),
                    required=bool(item.get("required", False)),
                    field_type=self.get_field_type(item),
                    allowed_values=self.get_allowed_values(item),
                )
            )
        return sorted(fields, key=lambda field: (not field.required, field.name.lower()))

    def parse_legacy_createmeta_fields(self, data, project_key, issue_type_id):
        for project in data.get("projects", []):
            if project.get("key") != project_key:
                continue
            for issue_type in project.get("issuetypes", []):
                if str(issue_type.get("id", "")) != str(issue_type_id):
                    continue
                fields = []
                for key, value in issue_type.get("fields", {}).items():
                    field_data = dict(value)
                    field_data["key"] = key
                    fields.append(field_data)
                return self.parse_fields(fields)
        return []

    def get_field_type(self, item):
        schema = item.get("schema") or {}
        field_type = schema.get("type") or schema.get("custom") or ""
        if schema.get("items"):
            field_type = f"{field_type}[{schema.get('items')}]"
        return field_type

    def get_allowed_values(self, item):
        values = []
        for value in item.get("allowedValues", [])[:10]:
            if isinstance(value, dict):
                values.append(value.get("name") or value.get("value") or value.get("key") or value.get("id", ""))
            else:
                values.append(str(value))
        return tuple(value for value in values if value)

    def create_issue(
        self,
        project,
        issue_type,
        summary,
        description_text,
        device_environment="",
        labels=None,
        fields=None,
        assignee=None,
        priority=None,
        reproducibility=None,
        test_environment=None,
        component=None,
    ):
        labels = labels or []
        fields = fields or []
        field_keys = {field.key for field in fields}

        base_fields = {
            "project": {"key": project.key},
            "issuetype": {"id": issue_type.id},
            "summary": summary,
        }

        if "description" in field_keys or not field_keys:
            base_fields["description"] = self.to_adf(description_text)
        if device_environment and "customfield_10400" in field_keys:
            base_fields["customfield_10400"] = self.to_adf(device_environment)
        if labels and "labels" in field_keys:
            base_fields["labels"] = labels
        if component and "components" in field_keys:
            base_fields["components"] = [{"name": component.name}]
        if assignee and "assignee" in field_keys:
            base_fields["assignee"] = self.format_assignee(assignee, cloud=True)
        if priority and "priority" in field_keys:
            base_fields["priority"] = {"name": priority}
        if reproducibility and "customfield_10028" in field_keys:
            base_fields["customfield_10028"] = [{"value": reproducibility}]
        if test_environment and "customfield_10027" in field_keys:
            base_fields["customfield_10027"] = [{"value": test_environment}]

        body = {"fields": base_fields}
        try:
            return self.request_json("POST", "/rest/api/3/issue", body=body)
        except JiraError as cloud_error:
            server_fields = dict(base_fields)
            server_fields["description"] = description_text
            if device_environment and "customfield_10400" in field_keys:
                server_fields["customfield_10400"] = device_environment
            if assignee and "assignee" in field_keys:
                server_fields["assignee"] = self.format_assignee(assignee, cloud=False)
            body = {"fields": server_fields}
            try:
                return self.request_json("POST", "/rest/api/2/issue", body=body)
            except JiraError:
                raise cloud_error

    def list_assignable_users(self, project, query=""):
        params = {"project": project.key, "maxResults": 100}
        if query:
            params["query"] = query
        try:
            data = self.request_json("GET", "/rest/api/3/user/assignable/search", params)
        except JiraError:
            params = {"project": project.key, "maxResults": 100}
            if query:
                params["username"] = query
            data = self.request_json("GET", "/rest/api/2/user/assignable/search", params)

        users = []
        for item in data:
            users.append(
                JiraUser(
                    account_id=item.get("accountId", ""),
                    name=item.get("name", ""),
                    display_name=item.get("displayName", ""),
                    email=item.get("emailAddress", ""),
                )
            )
        return sorted(users, key=lambda user: user.display_label.lower())

    def list_components(self, project):
        try:
            data = self.request_json("GET", f"/rest/api/3/project/{project.key}/components")
        except JiraError:
            data = self.request_json("GET", f"/rest/api/2/project/{project.key}/components")
        components = []
        for item in data:
            components.append(JiraComponent(id=str(item.get("id", "")), name=item.get("name", "")))
        return sorted(components, key=lambda component: component.name.lower())

    def list_labels(self):
        for path in ("/rest/api/3/label", "/rest/api/2/label"):
            try:
                data = self.request_json("GET", path, {"maxResults": 1000})
                values = data.get("values", data if isinstance(data, list) else [])
                return sorted({str(value) for value in values if value})
            except JiraError:
                continue
        return []

    def format_assignee(self, assignee, cloud=True):
        if cloud and assignee.account_id:
            return {"id": assignee.account_id}
        if assignee.name:
            return {"name": assignee.name}
        if assignee.account_id:
            return {"id": assignee.account_id}
        return {"name": assignee.display_name}

    def to_adf(self, text):
        content = []
        for line in text.splitlines() or [""]:
            if line.strip():
                content.append(
                    {
                        "type": "paragraph",
                        "content": [{"type": "text", "text": line}],
                    }
                )
            else:
                content.append({"type": "paragraph"})
        return {"type": "doc", "version": 1, "content": content}

    def upload_attachments(self, issue_key, file_paths):
        uploaded = []
        for file_path in file_paths:
            path = Path(file_path)
            if not path.exists() or not path.is_file():
                continue
            uploaded.extend(self.upload_attachment(issue_key, path))
        return uploaded

    def upload_attachment(self, issue_key, file_path):
        boundary = f"----qa-issue-collector-{uuid.uuid4().hex}"
        content_type = mimetypes.guess_type(file_path.name)[0] or "application/octet-stream"
        file_bytes = file_path.read_bytes()

        body = b"".join(
            [
                f"--{boundary}\r\n".encode("utf-8"),
                f'Content-Disposition: form-data; name="file"; filename="{file_path.name}"\r\n'.encode("utf-8"),
                f"Content-Type: {content_type}\r\n\r\n".encode("utf-8"),
                file_bytes,
                b"\r\n",
                f"--{boundary}--\r\n".encode("utf-8"),
            ]
        )

        return self.request_raw(
            "POST",
            f"/rest/api/3/issue/{issue_key}/attachments",
            body,
            f"multipart/form-data; boundary={boundary}",
            extra_headers={"X-Atlassian-Token": "no-check"},
        )
