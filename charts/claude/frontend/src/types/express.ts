import { Request } from 'express';

export interface RequestWithRequestId extends Request {
  requestId?: string;
}