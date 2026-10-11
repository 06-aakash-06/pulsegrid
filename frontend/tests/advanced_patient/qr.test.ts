import { describe, expect, it } from "vitest";
import QRCode from "qrcode";
import { BinaryBitmap, HybridBinarizer, QRCodeReader, RGBLuminanceSource } from "@zxing/library";

describe("check-in QR encoding", () => {
  it("round-trips the opaque same-origin link with a real decoder", () => {
    const link = "http://localhost:8080/patient/check-in#appointment_id=51&token=0123456789ABCDEFGHIJKL";
    const symbol = QRCode.create(link, { errorCorrectionLevel: "M" });
    const scale = 5, margin = 4;
    const width = (symbol.modules.size + 2 * margin) * scale;
    const pixels = new Uint8ClampedArray(width * width).fill(255);
    for (let y = 0; y < symbol.modules.size; y++) for (let x = 0; x < symbol.modules.size; x++) {
      if (!symbol.modules.get(y, x)) continue;
      for (let dy = 0; dy < scale; dy++) for (let dx = 0; dx < scale; dx++) {
        pixels[((y + margin) * scale + dy) * width + (x + margin) * scale + dx] = 0;
      }
    }
    const bitmap = new BinaryBitmap(new HybridBinarizer(new RGBLuminanceSource(pixels, width, width)));
    expect(new QRCodeReader().decode(bitmap).getText()).toBe(link);
  });
});
