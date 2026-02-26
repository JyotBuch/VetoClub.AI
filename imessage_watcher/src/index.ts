#!/usr/bin/env tsx
import { IMessageSDK } from '@photon-ai/imessage-kit';
import fetch from 'node-fetch';
import { config } from './config.js';
import { logger } from './utils/logger.js';
import { startBridgeServer } from './server.js';
import { IncomingMessage } from './types.js';

const sdk = new IMessageSDK({
  watcher: {
    pollInterval: config.pollIntervalMs,
    excludeOwnMessages: !config.includeSelfMessages
  }
});

async function main() {
  logger.info('Starting Photon watcher', {
    groupChatGuid: config.groupChatGuid,
    pollInterval: config.pollIntervalMs
  });

  await startBridgeServer({
    host: config.bridgeHost,
    port: config.bridgePort,
    sharedSecret: config.sharedSecret,
    send: async ({ chatGuid, text }) => sendWithAppleScript(chatGuid, text)
  });

  await sdk.startWatching({
    onMessage: onPhotonMessage,
    onError: (error) => {
      logger.error('Photon watcher error', { error: error instanceof Error ? error.message : String(error) });
    }
  });
}

function resolveSenderName(message: any): string {
  const candidates = [
    message.senderName,
    message.sender?.displayName,
    message.sender?.name,
    message.sender?.address,
    message.sender?.handle,
    message.handle,
    message.handleId,
    message.participant?.displayName,
    message.participant?.name,
    message.participant?.address,
    typeof message.sender === 'string' ? message.sender : undefined
  ];

  const rawSender = typeof message.sender === 'string' ? message.sender.trim() : undefined;
  if (rawSender && config.senderMap[rawSender]) {
    return config.senderMap[rawSender];
  }

  for (const candidate of candidates) {
    if (typeof candidate === 'string' && candidate.trim().length > 0) {
      return candidate.trim();
    }
  }

  return 'Unknown';
}

async function onPhotonMessage(message: any) {

  logger.info('Raw Photon message', { raw: JSON.stringify(message) }); // ← add this

  const normalized: IncomingMessage = {
    rowId: message.rowId,
    guid: message.guid ?? '',
    text: message.text ?? null,
    senderName: resolveSenderName(message),
    isFromMe: Boolean(message.isFromMe),
    timestamp: message.timestamp ? new Date(message.timestamp) : new Date(),
    chatId: message.chatId ?? ''
  };

  if (!normalized.text) {
    logger.debug('Skipping message without text', { guid: normalized.guid });
    return;
  }

  if (!config.includeSelfMessages && normalized.isFromMe) {
    logger.debug('Skipping self message', { guid: normalized.guid });
    return;
  }

  if (!normalized.chatId.includes(config.groupChatGuid)) {
    logger.debug('Skipping unrelated chat', { chatId: normalized.chatId });
    return;
  }

  await forwardToAgent(normalized);
}

async function forwardToAgent(message: IncomingMessage) {
  try {
    const payload = {
      message: {
        chatGuid: message.chatId,
        text: message.text,
        senderDisplayName: message.senderName,
        sender: message.senderName,
        isFromMe: message.isFromMe
      },
      source: 'photon_sdk'
    };

    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), config.forwardTimeoutMs);

    const response = await fetch(config.agentWebhookUrl, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        ...(config.sharedSecret ? { 'x-bridge-token': config.sharedSecret } : {})
      },
      body: JSON.stringify(payload),
      signal: controller.signal
    });

    clearTimeout(timeout);

    if (!response.ok) {
      logger.warn('Agent webhook returned non-200', { status: response.status });
    }
  } catch (error) {
    logger.error('Failed to forward message to agent', {
      error: error instanceof Error ? error.message : String(error)
    });
  }
}

async function sendWithAppleScript(chatGuid: string, text: string) {
  const { exec } = await import('child_process');
  const { promisify } = await import('util');
  const execAsync = promisify(exec);

  const safeText = text
    .replace(/\\/g, '\\\\')
    .replace(/"/g, '\\"')
    .replace(/\n/g, '\\n')
    .replace(/\r/g, '\\r');

  const script = `
tell application "Messages"
    set targetChat to first chat whose id contains "${chatGuid}"
    send "${safeText}" to targetChat
end tell
`;

  await execAsync(`osascript -e '${script.replace(/'/g, "'\\''")}'`);
}

main().catch((error) => {
  logger.error('Watcher failed to start', { error: error instanceof Error ? error.message : String(error) });
  process.exit(1);
});
