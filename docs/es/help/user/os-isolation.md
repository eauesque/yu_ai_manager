# Guía de aislamiento a nivel de SO

Función que restringe el impacto de las extensiones en el sistema usando los mecanismos de seguridad del SO.

## 1. Qué es el aislamiento de SO

Al instalar una aplicación en un smartphone, aparece "Esta aplicación solicita acceso a la cámara", ¿verdad? El aislamiento de SO sigue el mismo concepto.

Basándose en los permisos declarados por la extensión (lectura/escritura de archivos, comunicación en red, ejecución de comandos externos, etc.), **el kernel del SO bloquea físicamente las operaciones no permitidas**.
Sin importar qué técnicas se usen en el código Python, las restricciones a nivel de kernel no se pueden eludir.

> **Nota**: Esta función es principalmente para usar de forma segura extensiones de terceros. Las extensiones `builtin-*` se tratan como de confianza (L0) y funcionan sin restricciones.

---

## 2. Plataformas compatibles

| SO | Método de aislamiento | Madurez |
|----|---------|--------|
| **Linux** | AppArmor (Control de Acceso Obligatorio) | Recomendado, listo para producción |
| **macOS** | sandbox-exec (Seatbelt) | Experimental (deprecado por Apple) |
| **Windows** | Token restringido + Job Object | Restricción básica de recursos |

Linux con AppArmor es el más completo y el entorno recomendado.

---

## 3. Configuración en Linux (AppArmor)

### 3.1 Qué es AppArmor

AppArmor es un módulo de seguridad integrado en el kernel Linux. Define en un perfil "qué archivos puede leer/escribir" y "si se permite la comunicación en red" para cada proceso, y el kernel lo aplica.

En Ubuntu / Debian generalmente está habilitado por defecto, pero en algunas distribuciones como Raspberry Pi OS se requiere habilitación manual.

### 3.2 Configuración automática

Se puede configurar todo en lote con el script de configuración incluido.

```bash
sudo bash scripts/setup-apparmor.sh
```

Este script hace lo siguiente:

1. **Verificar/instalar paquetes AppArmor** — Instalación automática si `apparmor`, `apparmor-utils` no están presentes
2. **Agregar parámetro del kernel** — Agregar `lsm=apparmor` a `/boot/firmware/cmdline.txt` (con copia de seguridad)
3. **Instalar regla sudoers** — Configurar para que solo el comando `apparmor_parser` pueda ejecutarse sin contraseña (privilegio mínimo)
4. **Habilitar servicio AppArmor** — Configurar inicio automático con systemd

> **Para entornos distintos de Raspberry Pi OS**: En entornos con GRUB, agregar manualmente `lsm=apparmor` a `GRUB_CMDLINE_LINUX` en `/etc/default/grub` y ejecutar `sudo update-grub` como indica el script.

### 3.3 Reinicio

Si se agregó el parámetro del kernel, se requiere un reinicio.

```bash
sudo reboot
```

### 3.4 Verificar funcionamiento

Después del reinicio, verificar si AppArmor está habilitado con los siguientes comandos.

```bash
# Verificar si el módulo del kernel está habilitado
cat /sys/module/apparmor/parameters/enabled
# → "Y" significa habilitado

# Lista de perfiles cargados
sudo aa-status
```

### 3.5 Habilitar en config.json

Después de confirmar que AppArmor funciona, agregar lo siguiente a `config.json`.

```json
{
  "os_isolation": {
    "enabled": true,
    "linux": {
      "apparmor": true
    }
  }
}
```

Con esto, al iniciar extensiones de terceros se generan y cargan automáticamente perfiles AppArmor.

---

## 4. Referencia de elementos de configuración

Control con la sección `os_isolation` de `config.json`.

```json
{
  "os_isolation": {
    "enabled": true,
    "linux": {
      "apparmor": true
    },
    "macos": {
      "sandbox_exec": false
    },
    "windows": {
      "restricted_token": true,
      "job_object": true,
      "job_limits": {
        "memory_mb": 512,
        "cpu_percent": 50,
        "max_processes": 10
      }
    }
  }
}
```

| Clave | Tipo | Predeterminado | Descripción |
|------|------|-----------|------|
| `enabled` | bool | `false` | Habilitar/deshabilitar toda la función de aislamiento de SO |
| `linux.apparmor` | bool | `true` | Usar perfil AppArmor |
| `macos.sandbox_exec` | bool | `false` | Usar macOS sandbox-exec (experimental) |
| `windows.restricted_token` | bool | `true` | Iniciar proceso con token restringido |
| `windows.job_object` | bool | `true` | Restringir recursos con Job Object |
| `windows.job_limits.memory_mb` | int | `512` | Memoria máxima por extensión (MB) |
| `windows.job_limits.cpu_percent` | int | `50` | Límite de uso de CPU por extensión (%) |
| `windows.job_limits.max_processes` | int | `10` | Número máximo de procesos que puede crear la extensión |

---

## 5. Correspondencia entre permisos de extensión y reglas AppArmor

Los perfiles AppArmor se generan automáticamente según los permisos declarados por la extensión en `extension.json`.

| Permiso de extensión | Control en AppArmor |
|---------------|-------------------|
| `db:read` | Solo lectura del directorio `data/` |
| `db:write` | Lectura/escritura del directorio `data/` |
| `fs:read:scan_roots` | Lectura de raíces de escaneo configuradas |
| `fs:write:any` | Lectura/escritura de todas las rutas |
| `network:local` | Permitir TCP/Unix socket (UDP denegado) |
| `network:internet` | Permitir TCP/UDP/Unix socket |
| `subprocess` | Permitir ejecución en `/usr/bin/`, `/bin/`, etc. |
| Sin permisos de red | TCP/UDP explícitamente denegados, solo socket Unix para IPC |
| Sin permisos subprocess | Ejecución en `/usr/bin/`, `/bin/`, etc. explícitamente denegada |

El propio directorio de la extensión (`extensions/<name>/`) siempre tiene lectura/escritura habilitada.

---

## 6. Verificación desde la API

El estado del aislamiento de SO se puede verificar desde la API.

```bash
curl -s http://localhost:5000/api/extensions/os-isolation-info | python -m json.tool
```

Ejemplo de respuesta (con Linux / AppArmor habilitado):

```json
{
  "platform": "linux",
  "available": true,
  "method": "apparmor",
  "details": {
    "apparmor_kernel": "enabled",
    "apparmor_tools": true,
    "apparmor_sudoers": true,
    "aa_exec_path": "/usr/sbin/aa-exec"
  }
}
```

Si `available` es `false`, el campo `setup` contiene los pasos de configuración.

---

## 7. Solución de problemas

### AppArmor no se habilita

```bash
cat /sys/module/apparmor/parameters/enabled
# → "N" o el archivo no existe
```

**Causa**: El parámetro del kernel no se ha aplicado.

**Solución**:
- Raspberry Pi OS: Verificar que `lsm=apparmor` está en `/boot/firmware/cmdline.txt` y reiniciar
- Entorno GRUB: Verificar `GRUB_CMDLINE_LINUX="... lsm=apparmor"` en `/etc/default/grub` y ejecutar `sudo update-grub && sudo reboot`

### Aparece "sudoers not configured" al iniciar la extensión

**Causa**: La regla NOPASSWD sudoers para `apparmor_parser` no está configurada.

**Solución**:
```bash
sudo bash scripts/setup-apparmor.sh
```

El script instala la regla necesaria en `/etc/sudoers.d/yu-ai-apparmor`.

### La extensión no funciona por permisos insuficientes

**Causa**: El permiso necesario no está declarado en `extension.json` de la extensión.

**Solución**: Agregar el permiso necesario a `permissions.required` en `extension.json` de la extensión, o conceder el permiso manualmente desde Settings > Extensions.

### Verificación manual del perfil AppArmor

Los perfiles generados se guardan en `/tmp/yu_ai_apparmor/`.

```bash
# Verificar el contenido del perfil
cat /tmp/yu_ai_apparmor/yu_ai_ext_<nombre_de_extensión>

# Lista de perfiles de YU AI Manager actualmente cargados
sudo aa-status | grep yu_ai_ext
```

---

## 8. Notas sobre seguridad

El aislamiento de SO es una parte de la defensa en profundidad. YU AI Manager garantiza la seguridad con las siguientes capas:

1. **Análisis estático** (Fase 1) — Análisis AST del código de la extensión al instalar, detectando importaciones peligrosas
2. **Control de permisos** (Fases 2-3) — Control con Proxy verificando permisos en el acceso vía ServiceRegistry
3. **Aislamiento de SO** (Fase 4) — Restricción forzada de archivos, red y ejecución de procesos a nivel de kernel

Solo el aislamiento de SO no puede eliminar todos los riesgos, pero combinado con otras capas de defensa, proporciona un entorno donde se pueden usar extensiones de terceros de forma segura.

Para instalar extensiones que no son de confianza, se recomienda usar un entorno Linux con el aislamiento de SO habilitado.
