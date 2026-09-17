const videoExts = ['.webm', '.mp4', '.avi', '.mov', '.mkv', '.m4v', '.ogv'];
const audioExts = ['.mp3', '.wav', '.ogg', '.m4a', '.aac', '.flac', '.opus'];
const animatedImageExts = ['.gif'];
const pdfExts = ['.pdf'];
const mediaMimeMap: Record<string, string> = {
  '.webm': 'video/webm', '.mp4': 'video/mp4', '.mov': 'video/quicktime',
  '.m4v': 'video/x-m4v', '.ogv': 'video/ogg', '.avi': 'video/x-msvideo',
  '.mkv': 'video/x-matroska', '.mp3': 'audio/mpeg', '.wav': 'audio/wav',
  '.ogg': 'audio/ogg', '.opus': 'audio/ogg', '.m4a': 'audio/mp4',
  '.aac': 'audio/aac', '.flac': 'audio/flac',
};

export interface MediaClassification {
  mediaExt: string;
  isVideo: boolean;
  isAudio: boolean;
  isAnimatedImage: boolean;
  isPdf: boolean;
  mediaMime: string;
}

export function classifyByPath(pathValue: unknown): MediaClassification {
  const lowerPath = String(pathValue || '').toLowerCase();
  const mediaExtMatch = lowerPath.match(/(\.[a-z0-9]+)$/);
  const mediaExt = mediaExtMatch ? mediaExtMatch[1] : '';
  const isVideo = videoExts.includes(mediaExt);
  const isAudio = audioExts.includes(mediaExt);
  const isAnimatedImage = animatedImageExts.includes(mediaExt);
  const isPdf = pdfExts.includes(mediaExt);
  return { mediaExt, isVideo, isAudio, isAnimatedImage, isPdf, mediaMime: mediaMimeMap[mediaExt] || '' };
}
