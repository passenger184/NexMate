"""Central administrator-configurable operational limits for NexMate.

Every numeric operational limit in the gateway exists in two layers::

    administrator-configured value   (NexMate Settings, Desk-editable)
            ↓ validated at save: inside the administrator-supported range
    effective_limit = min(admin_configured_value, immutable_service_ceiling)
            ↓ enforced at runtime, ceiling re-checked as defense-in-depth
    enforcement

The service ceilings below are constants. They are **never** editable through
``NexMate Settings``, site configuration, the request, the browser, or
inference. Settings validation rejects out-of-range values at save time;
runtime enforcement clamps independently, so a malformed or bypassing value
that reaches runtime is still bounded rather than honored.

Security invariants (capability model, allowlists, projection attribute set,
audit vocabulary, protocol shapes, secrets) are deliberately absent here: they
are not limits and must never become settings. See design D21.

This module is dependency-free apart from a guarded ``frappe`` import so it
can be unit-tested offline: every function that touches Frappe degrades to a
documented safe value when Frappe is unavailable.
"""

try:  # pragma: no cover - exercised only inside a real Frappe process
	import frappe
except Exception:  # pragma: no cover - offline import guard
	frappe = None  # type: ignore[assignment]

SETTINGS_DOCTYPE = "NexMate Settings"
ROLE_RULES_FIELD = "developer_role_rules"

# ---------------------------------------------------------------------------
# Immutable service ceilings. Never configurable. Raising any of these is a
# reviewed product/security decision, not an administrator action.
# ---------------------------------------------------------------------------

SCHEMA_FIELDS_CEILING = 500
SCHEMA_BYTES_CEILING = 131072
READ_ROWS_CEILING = 100
READ_FIELDS_CEILING = 50
READ_BYTES_CEILING = 131072
READ_ROUNDS_CEILING = 5

# ---------------------------------------------------------------------------
# Defaults applied while a setting is unconfigured.
# ---------------------------------------------------------------------------

DEFAULT_SCHEMA_FIELDS = 300
DEFAULT_SCHEMA_BYTES = 65536
DEFAULT_READ_ROWS = 20
DEFAULT_READ_FIELDS = 20
DEFAULT_READ_BYTES = 65536
DEFAULT_READ_ROUNDS = 3

# ---------------------------------------------------------------------------
# Administrator-supported ranges: fieldname -> (minimum, administrator max).
# The administrator max equals the service ceiling in every case, so Settings
# validation and runtime clamping agree by construction.
# ---------------------------------------------------------------------------

NUMERIC_RANGES = {
	"max_schema_fields": (1, 500),
	"max_schema_bytes": (4096, 131072),
	"max_read_rows": (1, 100),
	"max_read_fields": (1, 50),
	"max_read_bytes": (4096, 131072),
	"max_read_rounds": (1, 5),
}

NUMERIC_DEFAULTS = {
	"max_schema_fields": DEFAULT_SCHEMA_FIELDS,
	"max_schema_bytes": DEFAULT_SCHEMA_BYTES,
	"max_read_rows": DEFAULT_READ_ROWS,
	"max_read_fields": DEFAULT_READ_FIELDS,
	"max_read_bytes": DEFAULT_READ_BYTES,
	"max_read_rounds": DEFAULT_READ_ROUNDS,
}

NUMERIC_CEILINGS = {
	"max_schema_fields": SCHEMA_FIELDS_CEILING,
	"max_schema_bytes": SCHEMA_BYTES_CEILING,
	"max_read_rows": READ_ROWS_CEILING,
	"max_read_fields": READ_FIELDS_CEILING,
	"max_read_bytes": READ_BYTES_CEILING,
	"max_read_rounds": READ_ROUNDS_CEILING,
}


# ---------------------------------------------------------------------------
# Settings access — uncached, fail-safe
# ---------------------------------------------------------------------------


def read_settings_doc():
	"""Return the site's ``NexMate Settings`` record, or None.

	Uncached on purpose: a committed change must affect the very next
	decision. Never raises: callers substitute defaults or deny.
	"""
	if frappe is None:  # pragma: no cover - offline guard
		return None
	try:
		return frappe.get_doc(SETTINGS_DOCTYPE, SETTINGS_DOCTYPE)
	except Exception:
		return None


def settings_is_configured():
	"""True only when the Settings record is proven saved on this site.

	A Single DocType that has never been saved is indistinguishable at the
	API level from one saved empty, so this checks the underlying store
	directly. ``False`` covers both "never saved" and "store unreadable";
	callers that must distinguish the two (developer-role fallback) use
	:func:`_settings_saved_state` instead.
	"""
	return _settings_saved_state() is True


def _settings_saved_state():
	"""Tri-state Settings persistence check: True, False, or None.

	- ``True``: the store proves the record was saved.
	- ``False``: the store proves it was never saved.
	- ``None``: the store could not be read. Unknown is neither configured
	  nor unconfigured, and callers must treat it as a failure, never as
	  absence.
	"""
	if frappe is None:  # pragma: no cover - offline guard
		return None
	try:
		rows = frappe.db.sql(
			"SELECT 1 FROM tabSingles WHERE doctype=%s LIMIT 1",
			SETTINGS_DOCTYPE,
		)
	except Exception:
		return None
	try:
		return bool(rows)
	except Exception:
		return None


# ---------------------------------------------------------------------------
# Numeric resolution
# ---------------------------------------------------------------------------


def coerce_limit(value, default, minimum, ceiling):
	"""Resolve one configured value to its effective limit.

	- ``None`` (unconfigured) → default.
	- Integer inside ``[minimum, ceiling]`` → the value.
	- Integer above the ceiling → clamped to the ceiling (defense in depth;
	  save-time validation should already have refused it).
	- Integer below the minimum, booleans, floats, strings and anything else
	  → default. A corrupt value must never widen behavior past the default,
	  and must never shrink it to a denial-of-service zero.

	A below-minimum integer resolves to the **default**, never to the
	minimum. Frappe materialises an unset ``Int`` on a Single as ``0`` on the
	write path, and collapsing that to the minimum would silently reduce a
	never-configured setting to its most restrictive value instead of its
	documented one. The default is the value that already governs an
	unconfigured setting, so resolving to it is neutral; the minimum is not.
	"""
	if value is None:
		return default
	if isinstance(value, bool):
		return default
	if isinstance(value, int):
		if value > ceiling:
			return ceiling
		if value < minimum:
			return default
		return value
	if isinstance(value, str):
		text = value.strip()
		if text.lstrip("+-").isdigit():
			try:
				number = int(text)
			except ValueError:
				return default
			if number > ceiling:
				return ceiling
			if number < minimum:
				return default
			return number
		return default
	return default


def _field_value(doc, fieldname):
	"""Read one settings field from a possibly-absent record."""
	if doc is None:
		return None
	try:
		return getattr(doc, fieldname, None)
	except Exception:
		return None


def effective_metadata_bounds(doc=None):
	"""Return ``(max_fields, max_bytes)`` for one metadata decision.

	Pass an already-loaded record to avoid a second store read; otherwise the
	record is read uncached here. ``None`` (unreadable settings) resolves
	everything to defaults.
	"""
	if doc is None:
		doc = read_settings_doc()
	fields = coerce_limit(
		_field_value(doc, "max_schema_fields"),
		DEFAULT_SCHEMA_FIELDS, 1, SCHEMA_FIELDS_CEILING,
	)
	size = coerce_limit(
		_field_value(doc, "max_schema_bytes"),
		DEFAULT_SCHEMA_BYTES, 4096, SCHEMA_BYTES_CEILING,
	)
	return fields, size


def effective_read_bounds(doc=None):
	"""Return ``(max_rows, max_fields, max_bytes)`` for one read decision."""
	if doc is None:
		doc = read_settings_doc()
	rows = coerce_limit(
		_field_value(doc, "max_read_rows"),
		DEFAULT_READ_ROWS, 1, READ_ROWS_CEILING,
	)
	fields = coerce_limit(
		_field_value(doc, "max_read_fields"),
		DEFAULT_READ_FIELDS, 1, READ_FIELDS_CEILING,
	)
	size = coerce_limit(
		_field_value(doc, "max_read_bytes"),
		DEFAULT_READ_BYTES, 4096, READ_BYTES_CEILING,
	)
	return rows, fields, size


def effective_rounds(doc=None):
	"""Return the effective inference → Frappe round budget for one ask."""
	if doc is None:
		doc = read_settings_doc()
	return coerce_limit(
		_field_value(doc, "max_read_rounds"),
		DEFAULT_READ_ROUNDS, 1, READ_ROUNDS_CEILING,
	)


def normalise_numeric_settings(getter, setter):
	"""Write the documented default into every unset numeric setting.

	Frappe's Single write path materialises an unset ``Int`` field as the
	string ``"0"`` (``Document.get_valid_dict``), even when the value the
	controller reads is still ``None`` — a Desk form posts ``null`` for an
	untouched ``Int``, and the ORM turns it into ``0`` on the way to the
	database. Storing that would leave a never-configured setting looking
	configured, which the ranges reject on the next save.

	Filling the documented default in while the value is still unset keeps an
	untouched save a genuine no-op: the stored state is exactly what an
	administrator sees before editing anything. Only ``None`` and blank are
	normalised. An explicitly configured value — including an explicit ``0`` —
	is left untouched for :func:`validate_numeric_settings` to judge, so
	genuinely invalid administrator input is still refused.

	``getter`` maps a fieldname to its current value; ``setter`` takes a
	fieldname and a value. Returns the list of fieldnames written.
	"""
	written = []
	for fieldname, default in NUMERIC_DEFAULTS.items():
		value = getter(fieldname)
		if value is None or (isinstance(value, str) and not value.strip()):
			setter(fieldname, default)
			written.append(fieldname)
	return written


def validate_numeric_settings(getter, throw):
	"""Validate every numeric setting; call ``throw(message)`` on violation.

	``getter`` maps a fieldname to its stored value so both real Documents
	and plain mappings can be validated. ``None`` and blank mean
	"unconfigured" and are always accepted (the default applies at runtime).
	Any other value must be an integer inside its supported range. An explicit
	out-of-range value is refused, including ``0``: after
	:func:`normalise_numeric_settings` has run, ``0`` in memory can only mean
	an administrator typed it.
	"""
	for fieldname, (minimum, maximum) in NUMERIC_RANGES.items():
		value = getter(fieldname)
		if value is None:
			continue
		if isinstance(value, str) and not value.strip():
			continue
		if isinstance(value, bool):
			throw(f"{fieldname} must be an integer between {minimum} and {maximum}")
			continue
		number = None
		if isinstance(value, int):
			number = value
		elif isinstance(value, str) and value.strip().lstrip("+-").isdigit():
			try:
				number = int(value.strip())
			except ValueError:
				number = None
		if number is None or not minimum <= number <= maximum:
			throw(f"{fieldname} must be an integer between {minimum} and {maximum}")


# ---------------------------------------------------------------------------
# Developer-role resolution — one authoritative path
# ---------------------------------------------------------------------------


def _site_config_roles():
	"""Raw ``site_config`` developer-role value. Never raises."""
	if frappe is None:  # pragma: no cover - offline guard
		return []
	try:
		conf = frappe.conf
	except Exception:
		return []
	try:
		return conf.get("nexmate_developer_roles", [])
	except Exception:
		return []


def resolve_developer_roles():
	"""Return ``(roles, source)`` for capability derivation. Never raises.

	- Settings proven saved with one or more roles → ``(names, "settings")``.
	- Settings proven saved with zero role rows → ``([], "settings")``: no
	  Developer roles are granted. This is explicit, not a fallback.
	- Settings proven never saved → the ``site_config`` value unchanged,
	  with source ``"site_config"``. This is the only fallback case. Note the
	  raw site_config value is passed through even when it is not a list, so
	  ``(None, "site_config")`` means "malformed site_config" while
	  ``(None, "unavailable")`` means "unreadable store": callers must branch
	  on the source, not on ``None``.
	- Settings persistence unknown (store unreadable), the record unreadable
	  despite proven persistence, or the role rows unreadable →
	  ``(None, "unavailable")``. Callers fail closed on ``None`` and must
	  NOT fall back to ``site_config``: an unreadable configuration is a
	  failure, not absence.

	"Configured" means the Settings record has ever been saved (checked
	against the store, since an unsaved Single is API-indistinguishable from
	an empty one). The store is read on every call: no cache, so role-source
	changes take effect on the next request. Row entries that are not strings
	are passed through untouched so downstream identity validation fails
	closed on them.
	"""
	saved = _settings_saved_state()
	if saved is False:
		return _site_config_roles(), "site_config"
	if saved is None:
		return None, "unavailable"
	try:
		doc = read_settings_doc()
	except Exception:
		return None, "unavailable"
	if doc is None:
		# Proven saved, yet the record cannot be read: failure, not absence.
		return None, "unavailable"
	try:
		rows = doc.get(ROLE_RULES_FIELD) or []
	except Exception:
		return None, "unavailable"
	names = []
	for row in rows:
		try:
			name = getattr(row, "target_role", None)
		except Exception:
			continue
		if isinstance(name, str) and name.strip():
			names.append(name.strip())
		elif name is not None:
			names.append(name)
	return names, "settings"
