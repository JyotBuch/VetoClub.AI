import 'dotenv/config';

const required = (value: string | undefined, name: string): string => {
  if (!value) {
    throw new Error(`Missing required environment variable: ${name}`);
  }
  return value;
};

const parseSenderMap = (raw: string | undefined): Record<string, string> => {
  if (!raw) {
    return {};
  }

  try {
    const parsed = JSON.parse(raw);
    if (parsed && typeof parsed === 'object') {
      const normalized: Record<string, string> = {};
      for (const [key, value] of Object.entries(parsed)) {
        if (typeof key === 'string' && typeof value === 'string') {
          normalized[key.trim()] = value.trim();
        }
      }
      return normalized;
    }
  } catch (error) {
    // Fall through to simple parsing below
  }

  return raw.split(',').reduce<Record<string, string>>((acc, pair) => {
    const [key, value] = pair.split('=').map((part) => part?.trim());
    if (key && value) {
      acc[key] = value;
    }
    return acc;
  }, {});
};

export const config = {
  groupChatGuid: required(process.env.PHOTON_GROUP_CHAT_GUID, 'PHOTON_GROUP_CHAT_GUID'),
  agentWebhookUrl: process.env.PHOTON_AGENT_WEBHOOK_URL ?? 'http://127.0.0.1:8000/webhook',
  bridgePort: parseInt(process.env.PHOTON_BRIDGE_PORT ?? '3001', 10),
  bridgeHost: process.env.PHOTON_BRIDGE_HOST ?? '127.0.0.1',
  pollIntervalMs: parseInt(process.env.PHOTON_POLL_INTERVAL_MS ?? '1500', 10),
  includeSelfMessages: process.env.PHOTON_INCLUDE_SELF === 'true',
  sharedSecret: process.env.PHOTON_SHARED_SECRET ?? '',
  forwardTimeoutMs: parseInt(process.env.PHOTON_FORWARD_TIMEOUT_MS ?? '1500', 10),
  senderMap: parseSenderMap(process.env.PHOTON_SENDER_MAP)
};
