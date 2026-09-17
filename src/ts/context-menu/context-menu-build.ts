import {
  actionAnalyze,
  actionCopyFilePath,
  actionCopyNAI,
  actionCopyNegative,
  actionCopyPositive,
  actionCopyRecipeParams,
  actionCopySD,
  actionFindSimilar,
  actionSaveToPromptLibrary,
  actionSendToBridge,
  actionSendWorkflowToComfyUI,
  actionSetRating,
  actionShowAppQR,
  actionShowDetail,
  actionShowQR,
  actionSnsShare,
  actionToggleFavorite,
} from './context-menu-actions';
import {
  actionOpenInExternalEditor,
  isArchiveMemberPath,
  isExternalEditorAvailable,
} from './external-editor';

export interface CardData {
  id: number;
  path: string;
  positive: string;
  negative: string;
}

type MenuAction = (data: CardData) => void;

export interface MenuItem {
  label: string;
  action?: MenuAction;
  separator?: boolean;
  submenu?: MenuItem[];
}

interface SeparatorItem {
  separator: true;
  label?: undefined;
}

export type MenuEntry = MenuItem | SeparatorItem;

export function buildMenuItems(data: CardData, tr: (key: string, fallback: string) => string): MenuEntry[] {
  const stars: MenuItem[] = [];
  for (let i = 1; i <= 5; i++) {
    const label = '\u2605'.repeat(i) + '\u2606'.repeat(5 - i);
    stars.push({ label, action: () => actionSetRating(data, i) });
  }
  stars.push({ label: tr('ctx.clear_rating', 'クリア'), action: () => actionSetRating(data, 0) });

  const editorEntries: MenuEntry[] =
    isExternalEditorAvailable() && !isArchiveMemberPath(data.path)
      ? [
          {
            label: tr('ctx.open_editor', '外部エディタで開く'),
            action: () => {
              void actionOpenInExternalEditor(data);
            },
          },
          { separator: true },
        ]
      : [];

  return [
    { label: tr('ctx.show_detail', '詳細を表示'), action: () => actionShowDetail(data) },
    { separator: true },
    { label: tr('ctx.copy_prompt', 'プロンプトをコピー'), action: () => actionCopyPositive(data) },
    { label: tr('ctx.copy_negative', 'ネガティブをコピー'), action: () => actionCopyNegative(data) },
    { label: tr('ctx.copy_sd', 'SD 形式でコピー'), action: () => actionCopySD(data) },
    { label: tr('ctx.copy_nai', 'NAI 形式でコピー'), action: () => actionCopyNAI(data) },
    { separator: true },
    { label: tr('ctx.favorite', 'お気に入り \u2606'), action: () => actionToggleFavorite(data) },
    { label: tr('ctx.rating', 'レーティング'), submenu: stars },
    { separator: true },
    {
      label: tr('ctx.send_bridge', 'Bridge に送る'),
      submenu: [
        { label: 'SD WebUI', action: () => actionSendToBridge(data, 'sd') },
        { label: 'ComfyUI', action: () => actionSendToBridge(data, 'comfy') },
        { label: 'NAI', action: () => actionSendToBridge(data, 'nai') },
        { label: tr('ctx.send_workflow_comfyui', 'ComfyUI ワークフロー'), action: () => actionSendWorkflowToComfyUI(data) },
      ],
    },
    { label: tr('ctx.save_pl', 'PL に保存'), action: () => actionSaveToPromptLibrary(data) },
    { separator: true },
    ...editorEntries,
    { label: tr('ctx.find_similar', '類似画像を探す'), action: () => actionFindSimilar(data) },
    { label: tr('ctx.qr_share', 'QR で共有'), action: () => actionShowQR(data) },
    { label: tr('ctx.sns_share', 'SNS で共有'), action: () => actionSnsShare(data) },
    { separator: true },
    { label: tr('ctx.recipe_copy', 'パラメータをコピー 📋'), action: () => actionCopyRecipeParams(data) },
    { label: tr('ctx.recipe_app_qr', 'App QR を生成 📱'), action: () => actionShowAppQR(data) },
    { separator: true },
    { label: tr('ctx.copy_path', 'ファイルパスをコピー'), action: () => actionCopyFilePath(data) },
    { label: tr('ctx.ai_analyze', 'AI 分析'), action: () => actionAnalyze(data) },
  ];
}
