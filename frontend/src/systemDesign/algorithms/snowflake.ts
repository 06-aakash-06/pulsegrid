export const EPOCH = Date.UTC(2026, 0, 1);
export function decodeSnowflake(id: bigint) {
  return { sign: 0, time: id >> 22n, worker: Number((id >> 12n) & 1023n), sequence: Number(id & 4095n) };
}
/** Browser allocator core; overflow waits for the next wall-clock millisecond.
 * It deliberately does not claim restart safety or cross-tab worker coordination. */
export class Snowflake {
  readonly worker: number;
  private last = -1;
  private wall = -1;
  private sequence = 0;
  constructor(service: number, replica: number) {
    if (!Number.isInteger(service) || service < 0 || service > 6 || !Number.isInteger(replica) || replica < 0 || replica > 127) throw new Error('Service must fit assigned codes zero through six; replica must fit seven bits.');
    this.worker = (service << 7) | replica;
  }
  next(now = Date.now()): bigint {
    const wall = now - EPOCH;
    if (!Number.isSafeInteger(wall) || wall < 0 || wall >= 2 ** 41) throw new Error('Time is outside the epoch range.');
    if (wall < this.wall) throw new Error('Clock moved backward.');
    this.wall = wall;
    const time = wall;
    const sequence = time === this.last ? this.sequence + 1 : time === 0 && this.worker === 0 ? 1 : 0;
    if (sequence > 4095) throw new Error('Sequence exhausted; wait for next millisecond.');
    this.sequence = sequence;
    if (time >= 2 ** 41) throw new Error('Time field exhausted.');
    this.last = time;
    return (BigInt(time) << 22n) | (BigInt(this.worker) << 12n) | BigInt(this.sequence);
  }
}

export async function generateSnowflakes(generator: Snowflake, count = 10000): Promise<bigint[]> {
  const ids: bigint[] = [];
  const deadline = performance.now() + 2000;
  while (ids.length < count) {
    try { ids.push(generator.next()); }
    catch (error) {
      if (!(error instanceof Error) || !error.message.startsWith('Sequence exhausted') || performance.now() > deadline) throw error;
      await new Promise(resolve => setTimeout(resolve, 1));
    }
  }
  return ids;
}
