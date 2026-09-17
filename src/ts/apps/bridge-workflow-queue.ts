/**
 * Shared helper for re-queuing a ComfyUI workflow from a saved image file.
 *
 * Flow:
 *  1. POST /ext/comfyui-bridge/api/check-workflow-from-file
 *  2. Show customConfirm if model nodes are missing or need supplement
 *  3. POST /ext/comfyui-bridge/api/queue-workflow-from-file (with supplement flag)
 */
import { customConfirm } from '../shared/dialog';
import { getAppApi, getNavApi } from '../shared/browser-apis';

interface CheckResult {
  status: 'ok' | 'supplement_available' | 'warning_no_backup';
  loader_type?: string;
  supplement_model_info?: {
    ckpt_name: string;
    diffusion_model: string;
    vae_name: string;
    text_encoder_1: string;
    text_encoder_2: string;
    clip_type: string;
  };
  message?: string;
}

interface QueueResult {
  prompt_id: string;
  comfyui_url: string;
  supplemented?: boolean;
  supplement_applied?: Record<string, string>;
}

export function sendWorkflowToComfyUI(fileId: number): void {
  const { apiFetch, tr } = getAppApi();
  const { showToast } = getNavApi();
  const _tr = (key: string, fb: string): string => tr(key, fb);

  void apiFetch('/ext/comfyui-bridge/api/check-workflow-from-file', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ file_id: fileId }),
  }).then(async (checkResp) => {
    const checkJson = await checkResp.json() as { ok: boolean; data?: CheckResult | null };
    if (!checkJson.ok) return;

    const checkData: CheckResult = checkJson.data ?? { status: 'ok' };
    let supplement = false;

    if (checkData.status === 'supplement_available') {
      const info = checkData.supplement_model_info;
      const model =
        info?.ckpt_name ||
        info?.diffusion_model ||
        _tr('bridge.supplement_model_unknown', '(不明)');
      const confirmed = await customConfirm(
        _tr(
          'bridge.supplement_confirm',
          'モデルノードが未設定です。バックアップ情報から補完して送りますか？',
        ) +
          '\n' +
          _tr('bridge.supplement_model_label', '補完モデル') +
          `: ${model}`,
      );
      if (!confirmed) return;
      supplement = true;
    } else if (checkData.status === 'warning_no_backup') {
      const confirmed = await customConfirm(
        _tr(
          'bridge.no_backup_warning',
          '⚠️ モデルノードが未設定で、バックアップ情報もありません。\nこのまま送ってもComfyUI側で手動設定が必要です。続けますか？',
        ),
      );
      if (!confirmed) return;
    }

    void apiFetch('/ext/comfyui-bridge/api/queue-workflow-from-file', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ file_id: fileId, supplement }),
    })
      .then(async (queueResp) => {
        const queueJson = await queueResp.json() as { ok: boolean; data?: QueueResult };
        if (!queueJson.ok) return;

        if (queueJson.data?.supplemented) {
          const applied = Object.entries(queueJson.data.supplement_applied ?? {})
            .map(([k, v]) => `${k}: ${v}`)
            .join(', ');
          showToast(
            _tr('bridge.queue_sent_supplemented', 'ワークフローを送信しました（補完: ') +
              applied +
              '）',
          );
        } else {
          showToast(_tr('bridge.queue_sent', 'ワークフローを ComfyUI に送信しました'));
        }
      })
      .catch((err: unknown) => {
        showToast(
          _tr('bridge.queue_failed', '送信に失敗しました') + ': ' + String(err),
        );
      });
  }).catch((err: unknown) => {
    showToast(
      _tr('bridge.check_failed', 'ワークフロー確認に失敗しました') + ': ' + String(err),
    );
  });
}
