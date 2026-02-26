import express from 'express';
import { logger } from './utils/logger.js';

interface BridgeServerOptions {
  host: string;
  port: number;
  sharedSecret?: string;
  send: (params: { chatGuid?: string; text: string }) => Promise<void>;
}

export async function startBridgeServer(options: BridgeServerOptions) {
  const app = express();
  app.use(express.json());

  app.get('/health', (_req, res) => {
    res.json({ status: 'ok', service: 'photon-bridge' });
  });

  app.post('/imessage/send', async (req, res) => {
    if (options.sharedSecret) {
      const token = req.header('x-bridge-token');
      if (token !== options.sharedSecret) {
        logger.warn('Rejected send request due to bad token');
        res.status(401).json({ error: 'unauthorized' });
        return;
      }
    }

    const { chatGuid, text } = req.body ?? {};
    if (typeof text !== 'string' || !text.trim()) {
      res.status(400).json({ error: 'text is required' });
      return;
    }

    const targetGuid = chatGuid || process.env.PHOTON_GROUP_CHAT_GUID;
    if (!targetGuid) {
      res.status(400).json({ error: 'chatGuid is required' });
      return;
    }

    try {
      await options.send({ chatGuid: targetGuid, text });
      res.json({ status: 'sent' });
    } catch (error) {
      logger.error('Failed to send message', { error: error instanceof Error ? error.message : String(error) });
      res.status(500).json({ error: 'failed_to_send' });
    }
  });

  return new Promise<void>((resolve) => {
    app.listen(options.port, options.host, () => {
      logger.info('Photon bridge server listening', { host: options.host, port: options.port });
      resolve();
    });
  });
}
