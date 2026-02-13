import { api } from './api';

// ---------------------------------------------------------------------------
//  Types
// ---------------------------------------------------------------------------

export interface IFileUploadResponse {
  id: string;
  filename: string;
  file_type: string;
  file_size_bytes: number;
  status: string;
  created_at: string;
}

export interface IUploadProgress {
  loaded: number;
  total: number;
  percentage: number;
}

// ---------------------------------------------------------------------------
//  Constants
// ---------------------------------------------------------------------------

export const ALLOWED_EXTENSIONS = [
  '.pcap',
  '.pcapng',
  '.cap',
  '.txt',
  '.conf',
  '.cfg',
  '.log',
  '.pdf',
  '.md',
];

export const MAX_FILE_SIZE_MB = 100;
const MAX_FILE_SIZE_BYTES = MAX_FILE_SIZE_MB * 1024 * 1024;

// ---------------------------------------------------------------------------
//  Validation
// ---------------------------------------------------------------------------

export function validateFile(file: File): string | null {
  const ext = '.' + file.name.split('.').pop()?.toLowerCase();

  if (!ALLOWED_EXTENSIONS.includes(ext)) {
    return `Extensao nao permitida (${ext}). Aceitas: ${ALLOWED_EXTENSIONS.join(', ')}`;
  }

  if (file.size > MAX_FILE_SIZE_BYTES) {
    return `Arquivo muito grande (${formatFileSize(file.size)}). Maximo: ${MAX_FILE_SIZE_MB}MB`;
  }

  return null;
}

// ---------------------------------------------------------------------------
//  Presigned upload types
// ---------------------------------------------------------------------------

interface IPresignResponse {
  document_id: string;
  presigned_url: string;
  object_key: string;
  expires_in: number;
}

// ---------------------------------------------------------------------------
//  Upload (3-step presigned flow)
// ---------------------------------------------------------------------------

export async function uploadFile(
  file: File,
  onProgress?: (progress: IUploadProgress) => void,
): Promise<IFileUploadResponse> {
  // Step 1: Get presigned URL
  const presignResponse = await api.post<IPresignResponse>('/files/presign', {
    filename: file.name,
    content_type: file.type || 'application/octet-stream',
    file_size_bytes: file.size,
  });
  const { document_id, presigned_url } = presignResponse.data;

  // Step 2: Upload directly to R2 via XHR (needed for cross-origin progress)
  await new Promise<void>((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open('PUT', presigned_url, true);
    xhr.setRequestHeader('Content-Type', file.type || 'application/octet-stream');

    xhr.upload.onprogress = (event) => {
      if (event.lengthComputable && onProgress) {
        onProgress({
          loaded: event.loaded,
          total: event.total,
          percentage: Math.round((event.loaded / event.total) * 100),
        });
      }
    };

    xhr.onload = () => {
      if (xhr.status >= 200 && xhr.status < 300) {
        resolve();
      } else {
        console.error('[R2 Upload] status:', xhr.status, 'response:', xhr.responseText);
        reject(new Error(`Upload falhou com status ${xhr.status}: ${xhr.responseText}`));
      }
    };

    xhr.onerror = () => {
      console.error('[R2 Upload] Network error (likely CORS). URL:', presigned_url.substring(0, 80));
      reject(new Error('Erro de rede durante upload (verifique CORS do R2)'));
    };
    xhr.send(file);
  });

  // Step 3: Confirm upload
  const confirmResponse = await api.post<IFileUploadResponse>('/files/confirm', {
    document_id,
  });
  return confirmResponse.data;
}

// ---------------------------------------------------------------------------
//  Helpers
// ---------------------------------------------------------------------------

export function formatFileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}
