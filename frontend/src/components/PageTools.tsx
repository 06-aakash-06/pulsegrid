import { createContext, useCallback, useContext, useEffect, useId, useRef, useState, type ButtonHTMLAttributes, type ReactNode } from "react";
import { createPortal } from "react-dom";

type Refresh = { run: () => void; disabled: () => boolean };
const Tools = createContext<{ register: (key: string, action: Refresh) => () => void; target: HTMLElement | null; headerSlot: HTMLElement | null; setHeaderSlot: (node: HTMLElement | null) => void } | null>(null);
const InAdvanced = createContext(false);
const InDetails = createContext(false);

export function PageToolsProvider({ children }: { children: ReactNode }) {
  const actions = useRef(new Map<string, Refresh>());
  const [count,setCount]=useState(0);
  const [target, setTarget] = useState<HTMLElement | null>(null);
  const [headerSlot, setHeaderSlot] = useState<HTMLElement | null>(null);
  const register = useCallback((key: string, action: Refresh) => { actions.current.set(key, action); setCount(actions.current.size); return () => { actions.current.delete(key); setCount(actions.current.size); }; }, []);
  const refresh = useCallback(() => { for (const action of actions.current.values()) if (!action.disabled()) action.run(); }, []);
  return <Tools.Provider value={{register, target, headerSlot, setHeaderSlot}}><HeaderRefresh.Provider value={count ? refresh : null}>{children}</HeaderRefresh.Provider>
    <details className="page-advanced" data-disclosure="advanced"><summary>Advanced lookup</summary><p>Use reference numbers only when a selection is unavailable.</p><div ref={setTarget} /></details>
  </Tools.Provider>;
}
const HeaderRefresh = createContext<(() => void) | null>(null);
export function PageHeaderSlot() { const tools=useContext(Tools);return <span className="page-header__slot" ref={tools?.setHeaderSlot} />; }
export function HeaderAction({ children }: {children:ReactNode}) { const tools=useContext(Tools);return tools ? tools.headerSlot ? createPortal(children,tools.headerSlot) : null : <>{children}</>; }
export function PageRefreshControl() { const refresh=useContext(HeaderRefresh);return refresh ? <button type="button" onClick={refresh}>Refresh</button> : null; }
/** Retains each existing callback without duplicating its control in the primary view. */
export function PageRefresh(props: ButtonHTMLAttributes<HTMLButtonElement>) {
  const tools=useContext(Tools), key=useId(), latest=useRef(props);latest.current=props;
  const register=tools?.register;
  useEffect(()=>register?.(key,{run:()=>latest.current.onClick?.({} as React.MouseEvent<HTMLButtonElement>),disabled:()=>!!latest.current.disabled}),[register,key]);
  return tools ? null : <button {...props} />;
}
export function AdvancedLookup({ title, children }: {title?:string;children:ReactNode}) {
  const tools=useContext(Tools), nested=useContext(InAdvanced);
  const content=<InAdvanced.Provider value={true}><section className="advanced-section">{title&&<h3>{title}</h3>}{children}</section></InAdvanced.Provider>;
  if(nested)return content;
  return tools ? tools.target ? createPortal(content,tools.target) : null : <details data-disclosure="advanced"><summary>Advanced lookup</summary>{content}</details>;
}
export function ItemDetails({ children }: {children:ReactNode}) {
  const nested=useContext(InDetails);
  return nested ? <>{children}</> : <details className="item-details" data-disclosure="details"><summary>Details</summary><InDetails.Provider value={true}><div className="item-details__body">{children}</div></InDetails.Provider></details>;
}
export function useInAdvanced(){return useContext(InAdvanced);}
export function useInDetails(){return useContext(InDetails);}
export function MoreActions({children,label="More actions"}:{children:ReactNode;label?:string}){return <details className="more-actions"><summary>{label}</summary>{children}</details>;}
