import { useEffect, useState } from "react";
import QRCode from "qrcode";

/** In-memory QR image. Only the opaque same-origin check-in link is encoded. */
export function CheckinQr({ value }: { value: string }) {
  const [image, setImage] = useState<string | null>(null);
  const [failed, setFailed] = useState(false);
  useEffect(() => {
    let active = true;
    setImage(null); setFailed(false);
    void QRCode.toString(value, { type: "svg", errorCorrectionLevel: "M", margin: 4 })
      .then(svg => { if (active) setImage(`data:image/svg+xml;charset=utf-8,${encodeURIComponent(svg)}`); })
      .catch(() => { if (active) setFailed(true); });
    return () => { active = false; };
  }, [value]);
  if (failed) return <p role="alert">QR image unavailable. Use the one-time token below.</p>;
  return image ? <img src={image} alt="Single-use appointment check-in QR" width={256} height={256} />
    : <p role="status">Preparing check-in QR…</p>;
}
