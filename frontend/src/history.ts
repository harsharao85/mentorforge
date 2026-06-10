// History API client — reads threads, messages, and artifacts from the
// MentorForgeLearnerMemory table via the Lambda Function URL (TASK-010).
// TASK-012: artifact bodies in S3; getArtifactUrl fetches a short-TTL presigned URL.

export interface Thread {
  threadId: string;
  title: string;
  created_at: string;
  last_active_at: string;
  msg_count: number;
}

export interface HistoryMessage {
  threadId: string;
  role: 'user' | 'assistant';
  text: string;
  tool_calls: { tool: string; result: string; latency_ms: number }[];
  ts: string;
}

export interface Artifact {
  artifactId: string;
  threadId: string;
  source: string;
  title: string;
  // New items (TASK-012): body in S3 — fetch via getArtifactUrl then the presigned URL.
  s3Key?: string;
  preview?: string;
  // Old items (pre-TASK-012): full body stored in DDB.
  content?: string;
  ts: string;
}

async function get<T>(url: string, idToken: string): Promise<T> {
  const resp = await fetch(url, {
    headers: { Authorization: `Bearer ${idToken}` },
  });
  if (!resp.ok) throw new Error(`History API ${resp.status}: ${await resp.text()}`);
  return resp.json() as Promise<T>;
}

export async function listThreads(apiUrl: string, idToken: string): Promise<Thread[]> {
  const data = await get<{ threads: Thread[] }>(`${apiUrl}threads`, idToken);
  return data.threads ?? [];
}

export async function getThreadMessages(
  apiUrl: string,
  idToken: string,
  threadId: string,
): Promise<HistoryMessage[]> {
  const data = await get<{ messages: HistoryMessage[] }>(
    `${apiUrl}threads/${encodeURIComponent(threadId)}/messages`,
    idToken,
  );
  return data.messages ?? [];
}

export async function listArtifacts(
  apiUrl: string,
  idToken: string,
  threadId: string,
): Promise<Artifact[]> {
  const data = await get<{ artifacts: Artifact[] }>(
    `${apiUrl}artifacts?threadId=${encodeURIComponent(threadId)}`,
    idToken,
  );
  return data.artifacts ?? [];
}

/** Fetch a short-TTL (5-min) presigned GET URL for an artifact body stored in S3.
 *  Ownership is validated server-side: the key must start with learners/<sub>/. */
export async function getArtifactUrl(
  apiUrl: string,
  idToken: string,
  s3Key: string,
): Promise<string> {
  const data = await get<{ url: string }>(
    `${apiUrl}artifact-url?key=${encodeURIComponent(s3Key)}`,
    idToken,
  );
  return data.url;
}
