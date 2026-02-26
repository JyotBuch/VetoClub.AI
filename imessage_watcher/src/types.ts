export interface IncomingMessage {
  rowId?: number;
  guid: string;
  text: string | null;
  senderName?: string;
  isFromMe: boolean;
  timestamp: Date;
  chatId: string;
}
