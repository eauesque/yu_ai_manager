// src/ts/shared/json-schema-validator.ts

/** i18n helper — falls back to English when window.tr is unavailable */
function _tr(key: string, fb: string, replacements?: Record<string, string>): string {
  const raw =
    typeof window !== 'undefined' &&
    typeof (window as { tr?: (k: string, fb: string) => string }).tr === 'function'
      ? (window as { tr: (k: string, fb: string) => string }).tr(key, fb)
      : fb;
  if (!replacements) return raw;
  return Object.entries(replacements).reduce((s, [k, v]) => s.replaceAll(`{${k}}`, v), raw);
}

/** Per-field schema definition */
export interface JsonFieldSchema {
  type: 'string' | 'number' | 'boolean' | 'object' | 'array' | 'null';
  required?: boolean;
  range?: { min?: number; max?: number };
  enum?: readonly unknown[];
  description?: string;
  items?: JsonFieldSchema;
  properties?: Record<string, JsonFieldSchema>;
  valueSchema?: JsonFieldSchema;
}

/** Object-level schema definition */
export interface JsonSchema {
  fields: Record<string, JsonFieldSchema>;
  allowUnknown?: boolean;
  applies?: (parsed: unknown) => boolean;
}

/** A single validation result */
export interface ValidationIssue {
  path: string;
  message: string;
  severity: 'error' | 'warning';
}

function validateValue(
  value: unknown,
  fieldSchema: JsonFieldSchema,
  path: string,
): ValidationIssue[] {
  const issues: ValidationIssue[] = [];

  // Step 1: type check
  const actual = value === null ? 'null' : Array.isArray(value) ? 'array' : typeof value;
  if (actual !== fieldSchema.type) {
    issues.push({
      path,
      message: _tr('json_doctor.err.type_mismatch', 'Expected {type} (got {actual})', {
        type: fieldSchema.type,
        actual,
      }),
      severity: 'error',
    });
    return issues; // No further checks if type is wrong
  }

  // Step 2: range (numbers only)
  if (fieldSchema.type === 'number' && fieldSchema.range) {
    const n = value as number;
    const { min, max } = fieldSchema.range;
    if ((min !== undefined && n < min) || (max !== undefined && n > max)) {
      issues.push({
        path,
        message: _tr('json_doctor.err.range', 'Must be between {min} and {max}', {
          min: String(min ?? '-∞'),
          max: String(max ?? '∞'),
        }),
        severity: 'error',
      });
    }
  }

  // Step 3: enum
  if (fieldSchema.enum !== undefined) {
    const allowed = fieldSchema.enum;
    if (!allowed.includes(value)) {
      issues.push({
        path,
        message: _tr('json_doctor.err.enum', 'Invalid value. Allowed: {values}', {
          values: allowed.map(v => String(v)).join(', '),
        }),
        severity: 'error',
      });
    }
  }

  // Step 4: object sub-validation
  if (
    fieldSchema.type === 'object' &&
    value !== null &&
    typeof value === 'object' &&
    !Array.isArray(value)
  ) {
    const obj = value as Record<string, unknown>;
    if (fieldSchema.properties) {
      // Recurse with synthetic schema. allowUnknown is intentionally NOT propagated —
      // nested unknown-key checks are out of scope (only top-level schema enforces allowUnknown).
      issues.push(...validateObject(obj, { fields: fieldSchema.properties }, path));
    }
    if (fieldSchema.valueSchema) {
      // Apply same schema to all values (arbitrary-key map, e.g. mcpServers)
      for (const [k, v] of Object.entries(obj)) {
        const childPath = path ? `${path}[${JSON.stringify(k)}]` : JSON.stringify(k);
        issues.push(...validateValue(v, fieldSchema.valueSchema, childPath));
      }
    }
  }

  // Step 5: array item validation
  if (fieldSchema.type === 'array' && Array.isArray(value) && fieldSchema.items) {
    (value as unknown[]).forEach((item, i) => {
      issues.push(...validateValue(item, fieldSchema.items!, `${path}[${i}]`));
    });
  }

  return issues;
}

function validateObject(
  obj: Record<string, unknown>,
  schema: JsonSchema,
  pathPrefix: string,
): ValidationIssue[] {
  const issues: ValidationIssue[] = [];

  // Check each defined field
  for (const [key, fieldSchema] of Object.entries(schema.fields)) {
    const path = pathPrefix ? `${pathPrefix}.${key}` : key;
    if (!(key in obj)) {
      if (fieldSchema.required) {
        issues.push({
          path,
          message: _tr('json_doctor.err.required', 'Required field is missing'),
          severity: 'error',
        });
      }
      continue;
    }
    issues.push(...validateValue(obj[key], fieldSchema, path));
  }

  // Check for unknown fields
  if (schema.allowUnknown === false) {
    for (const key of Object.keys(obj)) {
      if (!(key in schema.fields)) {
        const path = pathPrefix ? `${pathPrefix}.${key}` : key;
        issues.push({
          path,
          message: _tr('json_doctor.warn.unknown_field', 'Unknown field'),
          severity: 'warning',
        });
      }
    }
  }

  return issues;
}

/**
 * Parse JSON text and validate against schema.
 * Returns [] on parse failure (caller handles syntax errors separately).
 * Returns [] if schema.applies returns false.
 */
export function validateJson(jsonText: string, schema: JsonSchema): ValidationIssue[] {
  let parsed: unknown;
  try {
    parsed = JSON.parse(jsonText);
  } catch {
    return [];
  }

  if (schema.applies && !schema.applies(parsed)) {
    return [];
  }

  if (typeof parsed !== 'object' || parsed === null || Array.isArray(parsed)) {
    return [
      {
        path: '',
        message: _tr('json_doctor.err.not_object', 'Expected an object'),
        severity: 'error',
      },
    ];
  }

  return validateObject(parsed as Record<string, unknown>, schema, '');
}
