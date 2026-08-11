"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import {
  confirmShoppingCartItem,
  confirmShoppingCartRegistered,
  generateShoppingCart,
  getLatestShoppingCart,
  getShoppingCart,
  getShoppingCartFillReview,
  getShoppingCartFillScreenshotUrl,
  getShoppingCartItemPreviewUrl,
  openShoppingCartFilledForm,
  openShoppingCartRegister,
  previewShoppingCart,
  startShoppingCartApply,
  type CartFillReview,
  type ShoppingCartItem,
  type ShoppingCartResponse,
} from "@/lib/api";

interface ShoppingCartPanelProps {
  userId: string;
  internJobIds: string[];
  initialCartId?: string | null;
}

const FILL_REVIEW_STEPS = [
  { id: "profile" as const, label: "拟填档案", hint: "Profile / 确认简历意图字段" },
  { id: "filled" as const, label: "已写入字段", hint: "ATS 上实际填充结果" },
  { id: "screenshot" as const, label: "页面截图", hint: "停在 Submit 前" },
  { id: "pause" as const, label: "暂停确认", hint: "Submit 未点击" },
];

type ItemTab = "resume" | "cover" | "fill";
type FillStep = (typeof FILL_REVIEW_STEPS)[number]["id"];

/** Module-level dedupe so React Strict Mode double-mount doesn't fire two batches. */
const inFlightBatches = new Map<string, Promise<ShoppingCartResponse>>();

function cartStorageKey(userId: string, idsKey: string): string {
  return `shopping-cart:v1:${userId}:${idsKey}`;
}

function rememberCartId(userId: string, idsKey: string, cartId: string) {
  try {
    sessionStorage.setItem(cartStorageKey(userId, idsKey), cartId);
  } catch {
    /* ignore */
  }
  if (typeof window === "undefined") return;
  try {
    const url = new URL(window.location.href);
    if (url.searchParams.get("cartId") !== cartId) {
      url.searchParams.set("cartId", cartId);
      window.history.replaceState({}, "", url.toString());
    }
  } catch {
    /* ignore */
  }
}

function readRememberedCartId(userId: string, idsKey: string): string | null {
  try {
    return sessionStorage.getItem(cartStorageKey(userId, idsKey));
  } catch {
    return null;
  }
}

function selectReadyDefaults(items: ShoppingCartItem[]): Record<string, boolean> {
  const nextMap: Record<string, boolean> = {};
  for (const item of items || []) {
    if (
      item.item_id &&
      item.ok &&
      (item.status === "ready_md" || item.status === "confirmed")
    ) {
      nextMap[item.item_id] = true;
    }
  }
  return nextMap;
}

function formatSeconds(ms?: number | null): string {
  if (ms == null || Number.isNaN(ms)) return "—";
  return `${(ms / 1000).toFixed(1)}s`;
}

function formatApplyError(error?: string | null): string {
  const e = (error || "").trim();
  if (!e) return "";
  if (e === "no_official_ats_url") {
    return "Jobright 未找到官方投递链接（无法自动打开 ATS）";
  }
  if (e === "captcha_required") {
    return "验证码无法自动完成，需自行注册公司账户";
  }
  return e;
}

function needsManualRegister(item: ShoppingCartItem): boolean {
  const apply = item.apply;
  if (!apply) return false;
  return Boolean(
    apply.needs_manual_register ||
      apply.error === "captcha_required" ||
      apply.manual_register_opened
  );
}

function applyStatusLabel(
  status?: string | null,
  apply?: {
    autofill_clicked?: boolean;
    phase3_done?: boolean;
    phase4_done?: boolean;
    email_masked?: string | null;
    needs_manual_register?: boolean;
    error?: string | null;
  } | null
): string {
  switch (status) {
    case "queued":
      return "投递排队中";
    case "navigating":
      return "打开 Jobright…";
    case "on_ats":
      return "已到 ATS";
    case "applying":
      return apply?.autofill_clicked || apply?.phase3_done
        ? "注册/登录中…"
        : "Apply / Autofill…";
    case "registered":
      return apply?.email_masked
        ? `已注册/登录 (${apply.email_masked})`
        : "已注册/登录";
    case "filled":
      return "表单填写中";
    case "ready_to_submit":
      return "✓ 可投递（待一键提交）";
    case "submitted":
      return "已提交";
    case "failed":
      return apply?.needs_manual_register || apply?.error === "captcha_required"
        ? "需自行注册账户"
        : "投递失败";
    case "idle":
    default:
      return "未开始投递";
  }
}

function applySortRank(item: ShoppingCartItem): number {
  const st = item.apply?.status || "idle";
  if (st === "ready_to_submit") return 0;
  if (st === "submitted") return 1;
  if (st === "filled" || st === "registered" || st === "on_ats" || st === "applying") return 2;
  if (st === "queued" || st === "navigating") return 3;
  if (st === "failed") return 8;
  if (item.status === "generating" || item.status === "stalled") return 6;
  if (item.status === "failed") return 9;
  return 5;
}

function itemShortLabel(item: ShoppingCartItem): string {
  const company = (item.company || "?").trim();
  const pos = (item.position || "").trim();
  const shortPos = pos.length > 36 ? `${pos.slice(0, 36)}…` : pos;
  return shortPos ? `${company} · ${shortPos}` : company;
}

export default function ShoppingCartPanel({
  userId,
  internJobIds,
  initialCartId = null,
}: ShoppingCartPanelProps) {
  const [previewItems, setPreviewItems] = useState<ShoppingCartItem[]>([]);
  const [previewLoading, setPreviewLoading] = useState(false);
  const [cart, setCart] = useState<ShoppingCartResponse | null>(null);
  const [refining, setRefining] = useState(false);
  const [applying, setApplying] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [applyMessage, setApplyMessage] = useState<string | null>(null);
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [tabByItem, setTabByItem] = useState<Record<string, ItemTab>>({});
  const [busyId, setBusyId] = useState<string | null>(null);
  const [fillReviewByItem, setFillReviewByItem] = useState<Record<string, CartFillReview>>({});
  const [fillStepByItem, setFillStepByItem] = useState<Record<string, FillStep>>({});
  const [fillLoadingId, setFillLoadingId] = useState<string | null>(null);
  const [openFormBusyId, setOpenFormBusyId] = useState<string | null>(null);
  const [openFormMessage, setOpenFormMessage] = useState<string | null>(null);
  const [registerBusyId, setRegisterBusyId] = useState<string | null>(null);
  const [confirmRegisterBusyId, setConfirmRegisterBusyId] = useState<string | null>(null);

  const [selectedApplyIds, setSelectedApplyIds] = useState<Record<string, boolean>>({});

  const idsKey = useMemo(() => internJobIds.join(","), [internJobIds]);
  const hasResult = Boolean(cart);
  const cartGenerating =
    cart?.status === "generating" ||
    (cart?.items || []).some((i) => i.status === "generating" || i.status === "stalled");
  const readyItems = useMemo(
    () =>
      (cart?.items || []).filter(
        (i) => i.ok && i.item_id && (i.status === "ready_md" || i.status === "confirmed")
      ),
    [cart?.items]
  );

  const applyRestoredCart = useCallback(
    (existing: ShoppingCartResponse) => {
      setCart(existing);
      setSelectedApplyIds(selectReadyDefaults(existing.items || []));
      if (existing.cart_id) rememberCartId(userId, idsKey, existing.cart_id);
      const firstReady = (existing.items || []).find(
        (i) => i.ok && i.item_id && (i.status === "ready_md" || i.status === "confirmed")
      );
      if (firstReady?.item_id) setExpandedId(firstReady.item_id);
    },
    [userId, idsKey]
  );

  const loadPreview = useCallback(async () => {
    if (!internJobIds.length || !userId) return;
    setPreviewLoading(true);
    setError(null);
    setApplyMessage(null);
    try {
      const res = await previewShoppingCart(internJobIds);
      setPreviewItems(res.items || []);

      // Restore finished/in-progress cart so remount doesn't dump user back to「待 Refine」.
      let restored: ShoppingCartResponse | null = null;
      const remembered = initialCartId || readRememberedCartId(userId, idsKey);
      if (remembered) {
        try {
          restored = await getShoppingCart(remembered, userId);
        } catch {
          restored = null;
        }
      }
      if (!restored) {
        try {
          restored = await getLatestShoppingCart(userId, internJobIds);
        } catch {
          restored = null;
        }
      }
      if (restored?.cart_id) {
        applyRestoredCart(restored);
      } else {
        setCart(null);
        setSelectedApplyIds({});
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load selected jobs");
      setPreviewItems([]);
      setCart(null);
    } finally {
      setPreviewLoading(false);
    }
  }, [internJobIds, userId, idsKey, initialCartId, applyRestoredCart]);

  useEffect(() => {
    void loadPreview();
  }, [userId, idsKey, loadPreview]);

  const refreshCart = useCallback(async () => {
    if (!cart?.cart_id || !userId) return;
    try {
      const next = await getShoppingCart(cart.cart_id, userId);
      setCart(next);
      if (next.cart_id) rememberCartId(userId, idsKey, next.cart_id);
      // Auto-select newly ready items for apply (keep prior unchecks).
      setSelectedApplyIds((prev) => {
        const nextMap = { ...prev };
        for (const item of next.items || []) {
          if (
            item.item_id &&
            item.ok &&
            (item.status === "ready_md" || item.status === "confirmed") &&
            nextMap[item.item_id] === undefined
          ) {
            nextMap[item.item_id] = true;
          }
        }
        return nextMap;
      });
    } catch {
      /* ignore poll errors */
    }
  }, [cart?.cart_id, userId, idsKey]);

  // Poll while batch is still generating (progressive ready items).
  useEffect(() => {
    if (!cart?.cart_id || !cartGenerating) return;
    const timer = window.setInterval(() => {
      void refreshCart();
    }, 2500);
    return () => window.clearInterval(timer);
  }, [cart?.cart_id, cartGenerating, refreshCart]);

  useEffect(() => {
    if (!cart?.cart_id) return;
    const queued = cart.apply_summary?.queued || 0;
    const navigating = cart.apply_summary?.navigating || 0;
    const onAts = cart.apply_summary?.on_ats || 0;
    const applyingActive = (cart.items || []).some(
      (i) => i.apply?.status === "applying" && !i.apply?.autofill_clicked && !i.apply?.phase3_done
    );
    if (queued + navigating + onAts <= 0 && !applyingActive) return;
    const timer = window.setInterval(() => {
      void refreshCart();
    }, 4000);
    return () => window.clearInterval(timer);
  }, [
    cart?.cart_id,
    cart?.apply_summary?.queued,
    cart?.apply_summary?.navigating,
    cart?.apply_summary?.on_ats,
    cart?.items,
    refreshCart,
  ]);

  const runGenerate = useCallback(async () => {
    if (!userId || !internJobIds.length || refining) return;
    const key = `${userId}::${idsKey}`;
    setRefining(true);
    setError(null);
    try {
      let pending = inFlightBatches.get(key);
      if (!pending) {
        pending = generateShoppingCart(userId, internJobIds).finally(() => {
          inFlightBatches.delete(key);
        });
        inFlightBatches.set(key, pending);
      }
      const res = await pending;
      setCart(res);
      if (res.cart_id) rememberCartId(userId, idsKey, res.cart_id);
      setSelectedApplyIds({});
      // Don't expand in-progress items — ok=false would look like a failure.
      const firstReady = (res.items || []).find(
        (i) => i.ok && i.item_id && (i.status === "ready_md" || i.status === "confirmed")
      );
      if (firstReady?.item_id) setExpandedId(firstReady.item_id);
      else setExpandedId(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Batch refine failed");
    } finally {
      setRefining(false);
    }
  }, [userId, internJobIds, idsKey, refining]);

  const onConfirm = async (item: ShoppingCartItem) => {
    if (!cart?.cart_id || !item.item_id) return;
    setBusyId(item.item_id);
    setError(null);
    try {
      const confirmed = await confirmShoppingCartItem(cart.cart_id, item.item_id, userId);
      setCart((prev) => {
        if (!prev) return prev;
        return {
          ...prev,
          items: (prev.items || []).map((row) =>
            row.item_id === item.item_id
              ? {
                  ...row,
                  status: "confirmed",
                  has_resume_pdf: true,
                  has_cover_letter_pdf: true,
                  folder: confirmed.folder,
                }
              : row
          ),
        };
      });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Confirm to PDF failed");
    } finally {
      setBusyId(null);
    }
  };

  const loadFillReview = async (item: ShoppingCartItem) => {
    if (!cart?.cart_id || !item.item_id) return;
    setFillLoadingId(item.item_id);
    try {
      const review = await getShoppingCartFillReview(cart.cart_id, item.item_id, userId);
      setFillReviewByItem((m) => ({ ...m, [item.item_id!]: review }));
      setFillStepByItem((m) => ({ ...m, [item.item_id!]: m[item.item_id!] || "profile" }));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Load fill review failed");
    } finally {
      setFillLoadingId(null);
    }
  };

  const openFilledForm = async (item: ShoppingCartItem) => {
    if (!cart?.cart_id || !item.item_id) return;
    setOpenFormBusyId(item.item_id);
    setOpenFormMessage(null);
    setError(null);
    try {
      const res = await openShoppingCartFilledForm(cart.cart_id, item.item_id, userId);
      if (res.refilled || res.session_restored) {
        setOpenFormMessage(
          res.message || "已在本机浏览器打开官网 ATS，并重新填入表单（Submit 未点击）"
        );
      } else if (res.form_url) {
        // No saved cookies — also open a tab so user can jump; may need Sign In
        window.open(res.form_url, "_blank", "noopener,noreferrer");
        setOpenFormMessage(
          res.message || "已打开官网表单页；无保存会话时可能需重新 Sign In"
        );
      } else {
        setOpenFormMessage(res.message || "已请求打开表单页");
      }
    } catch (err) {
      const formUrl = item.apply?.form_url || item.apply?.ats_url;
      if (formUrl) {
        window.open(formUrl, "_blank", "noopener,noreferrer");
        setOpenFormMessage("后端打开失败，已用浏览器新标签打开表单 URL（可能无登录态）");
      } else {
        setError(err instanceof Error ? err.message : "打开表单失败");
      }
    } finally {
      setOpenFormBusyId(null);
    }
  };

  const openManualRegister = async (item: ShoppingCartItem) => {
    if (!cart?.cart_id || !item.item_id) return;
    setRegisterBusyId(item.item_id);
    setOpenFormMessage(null);
    setError(null);
    try {
      const res = await openShoppingCartRegister(cart.cart_id, item.item_id, userId);
      setOpenFormMessage(
        res.message ||
          (res.focused_existing
            ? "已聚焦 ATS 注册窗口，请完成验证码并注册"
            : "已打开 ATS 注册页，请亲自完成注册后点「已注册完成」")
      );
      await refreshCart();
    } catch (err) {
      const atsUrl = item.apply?.ats_url;
      if (atsUrl) {
        window.open(atsUrl, "_blank", "noopener,noreferrer");
        setOpenFormMessage("后端打开失败，已用浏览器新标签打开 ATS（请自行注册后点「已注册完成」）");
      } else {
        setError(err instanceof Error ? err.message : "打开注册页失败");
      }
    } finally {
      setRegisterBusyId(null);
    }
  };

  const confirmManualRegister = async (item: ShoppingCartItem) => {
    if (!cart?.cart_id || !item.item_id) return;
    setConfirmRegisterBusyId(item.item_id);
    setOpenFormMessage(null);
    setError(null);
    try {
      const res = await confirmShoppingCartRegistered(cart.cart_id, item.item_id, userId, true);
      setApplyMessage(res.message || "已确认注册，继续自动投递中…");
      if (res.phase5 && res.phase5.ok === false) {
        setError(
          (res.phase5 as { apply?: { error?: string }; error?: string }).apply?.error ||
            (res.phase5 as { error?: string }).error ||
            "注册后继续填表失败"
        );
      }
      await refreshCart();
    } catch (err) {
      setError(err instanceof Error ? err.message : "确认注册失败");
    } finally {
      setConfirmRegisterBusyId(null);
    }
  };

  const onStartApply = async () => {
    if (!cart?.cart_id || applying) return;
    const selected = readyItems
      .map((i) => i.item_id!)
      .filter((id) => selectedApplyIds[id] !== false);
    if (!selected.length) {
      setError("请先勾选已生成完成的职位再投递");
      return;
    }
    setApplying(true);
    setError(null);
    setApplyMessage(null);
    try {
      const res = await startShoppingCartApply(cart.cart_id, userId, selected);
      setApplyMessage(
        res.message ||
          `已处理投递：排队 ${res.queued_count}` +
            (res.ok_count != null ? ` · 到达 ATS ${res.ok_count}` : "") +
            (res.failed_count ? ` · 失败 ${res.failed_count}` : "")
      );
      await refreshCart();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Start apply failed");
    } finally {
      setApplying(false);
    }
  };

  const listItems = useMemo(() => {
    const raw = hasResult ? cart?.items || [] : previewItems;
    if (!hasResult) return raw;
    return [...raw].sort((a, b) => applySortRank(a) - applySortRank(b));
  }, [hasResult, cart?.items, previewItems]);
  const readyToSubmitItems = useMemo(
    () => (cart?.items || []).filter((i) => i.apply?.status === "ready_to_submit"),
    [cart?.items]
  );
  const applyFailedItems = useMemo(
    () => (cart?.items || []).filter((i) => i.apply?.status === "failed"),
    [cart?.items]
  );
  const manualRegisterItems = useMemo(
    () => applyFailedItems.filter((i) => needsManualRegister(i)),
    [applyFailedItems]
  );
  const pendingCount = previewItems.filter((i) => i.ok !== false || i.status === "pending").length;
  const canRefine =
    !refining && !hasResult && previewItems.some((i) => i.ok !== false && i.status !== "unresolved");
  const selectedReadyCount = readyItems.filter(
    (i) => i.item_id && selectedApplyIds[i.item_id] !== false
  ).length;
  const canStartApply = Boolean(cart?.cart_id) && selectedReadyCount > 0 && !applying;

  return (
    <div
      className={`space-y-4 ${!hasResult ? "pb-24" : "pb-8"}`}
      data-testid="shopping-cart-panel"
      data-cart-id={cart?.cart_id || ""}
    >
      <div className="rounded-2xl border border-emerald-200 bg-emerald-50 px-4 py-3 text-xs text-emerald-950">
        {hasResult
          ? cartGenerating
            ? "渐进生成中：已完成的职位可先预览/确认/投递；慢的或卡住的不会挡住其它职位。"
            : "生成完成：下方以 PDF 预览（未落盘）。点「确认最终版」后才写入公司_职位文件夹，然后可投递已勾选职位。"
          : "先确认已选职位，再点底部「批量 Refine」。生成过程中会陆续出现结果，无需等全部结束。"}
        {cart ? (
          <span className="ml-2">
            成功 {cart.ok_count ?? readyItems.length}/{cart.requested ?? listItems.length}
            {cart.generating_count ? ` · 进行中 ${cart.generating_count}` : ""}
            {cart.failed_count ? ` · 失败 ${cart.failed_count}` : ""}
            {cart.concurrency ? ` · 并发 ${cart.concurrency}` : ""}
            {cart.elapsed_ms != null && !cartGenerating
              ? ` · 总耗时 ${formatSeconds(cart.elapsed_ms)}`
              : ""}
          </span>
        ) : null}
      </div>

      {hasResult ? (
        <div
          className="flex flex-wrap items-center justify-between gap-3 rounded-2xl border border-slate-200 bg-white px-4 py-3 shadow-sm"
          data-testid="cart-apply-bar"
        >
          <div className="min-w-0 flex-1 text-xs text-slate-600">
            {cartGenerating ? (
              <span className="mr-2 rounded bg-amber-100 px-1.5 py-0.5 text-amber-900">
                仍有职位生成中
              </span>
            ) : null}
            勾选待自动投递 {selectedReadyCount}/{readyItems.length}
            {" · "}queued {cart?.apply_summary?.queued ?? 0}
            {" · "}可提交 {cart?.apply_summary?.ready_to_submit ?? 0}
            {" · "}投递失败 {cart?.apply_summary?.failed ?? 0}
            {readyToSubmitItems.length ? (
              <div className="mt-1 text-emerald-800" data-testid="cart-ready-to-submit-list">
                可投递：
                {readyToSubmitItems.map((i) => itemShortLabel(i)).join("；")}
                <button
                  type="button"
                  className="ml-2 underline"
                  onClick={() => {
                    const id = readyToSubmitItems[0]?.item_id;
                    if (id) setExpandedId(id);
                  }}
                >
                  定位
                </button>
              </div>
            ) : null}
            {manualRegisterItems.length ? (
              <div className="mt-1 text-amber-900" data-testid="cart-manual-register-list">
                需自行注册账户（验证码）：
                {manualRegisterItems
                  .map(
                    (i) =>
                      `${itemShortLabel(i)}（${
                        i.apply?.manual_register_reason ||
                        formatApplyError(i.apply?.error) ||
                        "需人工注册"
                      }）`
                  )
                  .join("；")}
              </div>
            ) : null}
            {applyFailedItems.filter((i) => !needsManualRegister(i)).length ? (
              <div className="mt-1 text-rose-800" data-testid="cart-apply-failed-list">
                其它投递失败：
                {applyFailedItems
                  .filter((i) => !needsManualRegister(i))
                  .map((i) => `${itemShortLabel(i)}（${formatApplyError(i.apply?.error) || "unknown"}）`)
                  .join("；")}
              </div>
            ) : null}
            {applyMessage ? <span className="mt-1 block text-emerald-800">{applyMessage}</span> : null}
            {openFormMessage ? (
              <span className="mt-1 block text-emerald-800" data-testid="cart-open-form-msg">
                {openFormMessage}
              </span>
            ) : null}
          </div>
          <button
            type="button"
            disabled={!canStartApply}
            data-testid="cart-start-apply-btn"
            className="rounded-xl bg-[#14352b] px-4 py-2 text-xs font-semibold text-white disabled:opacity-40"
            onClick={() => void onStartApply()}
          >
            {applying ? "导航 ATS 中…" : `投递已勾选（${selectedReadyCount}）`}
          </button>
          <button
            type="button"
            disabled={refining || cartGenerating}
            data-testid="cart-re-refine-btn"
            className="rounded-xl border border-slate-300 bg-white px-3 py-2 text-xs font-semibold text-slate-700 disabled:opacity-40"
            onClick={() => void runGenerate()}
            title="会新建一轮生成，覆盖当前购物车视图"
          >
            {refining ? "重新生成中…" : "重新 Refine"}
          </button>
        </div>
      ) : null}

      {previewLoading ? (
        <div className="rounded-3xl border border-slate-200 bg-white p-8 text-center text-sm text-slate-600 shadow-sm">
          正在加载已选职位…
        </div>
      ) : null}

      {refining && !hasResult ? (
        <div className="rounded-3xl border border-slate-200 bg-white p-8 text-center text-sm text-slate-600 shadow-sm">
          正在创建购物车并启动批量生成…
        </div>
      ) : null}

      {error ? (
        <div className="rounded-xl border border-rose-200 bg-rose-50 px-3 py-2 text-xs text-rose-900">
          {error}
          <button
            type="button"
            className="ml-3 underline"
            onClick={() => void (hasResult || refining ? runGenerate() : loadPreview())}
          >
            重试
          </button>
        </div>
      ) : null}

      {!previewLoading && !refining && !listItems.length && !error ? (
        <p className="text-sm text-slate-500">购物车为空 — 请从 intern-list 勾选职位后进入。</p>
      ) : null}

      <section className="space-y-3" data-testid="shopping-cart-list">
        {listItems.map((item, idx) => {
          const key = item.item_id || item.intern_job_id || String(idx);
          const open = expandedId === item.item_id || expandedId === key;
          const tab = tabByItem[key] || "resume";
          const isReady =
            Boolean(item.ok) && (item.status === "ready_md" || item.status === "confirmed");
          const statusLabel =
            item.status === "stalled"
              ? "生成较慢（仍在后台）"
              : item.status === "generating"
                ? "生成中…"
                : item.status || (item.ok ? (hasResult ? "ready_md" : "pending") : "failed");
          const applySt = item.apply?.status || "idle";
          const applyErr = formatApplyError(item.apply?.error);
          return (
            <div
              key={key}
              className={`overflow-hidden rounded-2xl border bg-white shadow-sm ${
                applySt === "ready_to_submit"
                  ? "border-emerald-400 ring-1 ring-emerald-200"
                  : applySt === "failed"
                    ? "border-rose-200"
                    : "border-slate-200"
              }`}
              data-testid={`cart-item-${key}`}
            >
              <div className="flex w-full items-start gap-2 px-4 py-3">
                {hasResult && item.item_id ? (
                  <label className="mt-1 shrink-0" onClick={(e) => e.stopPropagation()}>
                    <input
                      type="checkbox"
                      className="h-4 w-4 rounded border-slate-300"
                      disabled={!isReady}
                      checked={isReady && selectedApplyIds[item.item_id] !== false}
                      data-testid={`cart-item-select-${item.item_id}`}
                      onChange={(e) => {
                        const id = item.item_id!;
                        setSelectedApplyIds((m) => ({ ...m, [id]: e.target.checked }));
                      }}
                    />
                  </label>
                ) : null}
              <button
                type="button"
                className="flex min-w-0 flex-1 items-start justify-between gap-3 text-left hover:bg-slate-50"
                onClick={() => {
                  if (!hasResult) return;
                  setExpandedId(open ? null : item.item_id || key);
                }}
              >
                <div className="min-w-0">
                  <div className="truncate text-sm font-bold text-slate-900">
                    {item.company || "?"} · {item.position || item.intern_job_id}
                  </div>
                  <div className="mt-0.5 text-[11px] text-slate-500">
                    {item.location || "—"}
                    {" · "}
                    <span data-testid="cart-item-status">{statusLabel}</span>
                    {hasResult ? (
                      <>
                        {" · "}
                        <span
                          data-testid="cart-item-apply-status"
                          className="font-semibold text-[#14352b]"
                        >
                          {applyStatusLabel(applySt, item.apply)}
                        </span>
                      </>
                    ) : null}
                    {item.has_detail === false ? " · 暂无 JD 详情" : ""}
                    {item.elapsed_ms != null ? ` · ${formatSeconds(item.elapsed_ms)}` : ""}
                    {item.status === "stalled" && item.error
                      ? ` · ${item.error}`
                      : item.error && item.status === "failed"
                        ? ` · ${item.error}`
                        : ""}
                    {applyErr ? ` · ${applyErr}` : ""}
                  </div>
                  {applySt === "ready_to_submit" ? (
                    <div className="mt-1 text-[11px] font-semibold text-emerald-700">
                      这条可以继续投递（表单已填好，待一键提交）
                    </div>
                  ) : null}
                  {needsManualRegister(item) && applySt === "failed" ? (
                    <div className="mt-1 text-[11px] font-semibold text-amber-900">
                      {item.apply?.manual_register_reason ||
                        formatApplyError(item.apply?.error) ||
                        "需要你自行完成公司账户注册"}
                    </div>
                  ) : null}
                  {item.apply?.jobright_url ? (
                    <a
                      href={item.apply.jobright_url}
                      target="_blank"
                      rel="noreferrer"
                      className="mt-1 inline-block text-[11px] font-semibold text-emerald-700 hover:underline"
                      onClick={(e) => e.stopPropagation()}
                    >
                      Jobright 页 →
                    </a>
                  ) : null}
                  {item.apply?.ats_url ? (
                    <a
                      href={item.apply.ats_url}
                      target="_blank"
                      rel="noreferrer"
                      className="mt-1 ml-2 inline-block text-[11px] font-semibold text-emerald-700 hover:underline"
                      onClick={(e) => e.stopPropagation()}
                      data-testid="cart-item-ats-url"
                    >
                      ATS{item.apply.ats_type ? ` (${item.apply.ats_type})` : ""} →
                    </a>
                  ) : null}
                  {(applySt === "ready_to_submit" ||
                    applySt === "filled" ||
                    item.apply?.phase5_done) &&
                  (item.apply?.form_url || item.apply?.ats_url) ? (
                    <button
                      type="button"
                      data-testid="cart-open-form-btn"
                      disabled={openFormBusyId === item.item_id}
                      className="mt-1 ml-2 inline-flex items-center rounded-lg bg-[#14352b] px-2.5 py-1 text-[11px] font-semibold text-white disabled:opacity-40"
                      onClick={(e) => {
                        e.stopPropagation();
                        void openFilledForm(item);
                      }}
                    >
                      {openFormBusyId === item.item_id ? "打开中…" : "查看表单"}
                    </button>
                  ) : null}
                </div>
                {hasResult ? (
                  <span className="shrink-0 text-xs text-slate-400">{open ? "收起" : "展开"}</span>
                ) : (
                  <span className="shrink-0 rounded-full bg-slate-100 px-2 py-0.5 text-[10px] font-semibold text-slate-600">
                    待 Refine
                  </span>
                )}
              </button>
              </div>
              {needsManualRegister(item) && applySt === "failed" ? (
                <div
                  className="flex flex-wrap items-center gap-2 border-t border-amber-100 bg-amber-50/80 px-4 py-2"
                  data-testid="cart-manual-register-actions"
                >
                  <button
                    type="button"
                    data-testid="cart-open-register-btn"
                    disabled={registerBusyId === item.item_id}
                    className="inline-flex items-center rounded-lg bg-amber-700 px-2.5 py-1 text-[11px] font-semibold text-white disabled:opacity-40"
                    onClick={() => void openManualRegister(item)}
                  >
                    {registerBusyId === item.item_id ? "打开中…" : "去注册"}
                  </button>
                  <button
                    type="button"
                    data-testid="cart-confirm-registered-btn"
                    disabled={confirmRegisterBusyId === item.item_id}
                    className="inline-flex items-center rounded-lg border border-amber-700 bg-white px-2.5 py-1 text-[11px] font-semibold text-amber-900 disabled:opacity-40"
                    onClick={() => void confirmManualRegister(item)}
                  >
                    {confirmRegisterBusyId === item.item_id ? "继续投递中…" : "已注册完成"}
                  </button>
                </div>
              ) : null}

              {open && item.ok && hasResult && cart?.cart_id && item.item_id ? (
                <div className="border-t border-slate-100 px-4 py-3">
                  <div className="mb-3 flex flex-wrap items-center gap-2">
                    <button
                      type="button"
                      className={`rounded-lg px-3 py-1.5 text-[11px] font-semibold ${
                        tab === "resume"
                          ? "bg-emerald-700 text-white"
                          : "border border-slate-200 text-slate-700"
                      }`}
                      onClick={() => setTabByItem((m) => ({ ...m, [key]: "resume" }))}
                    >
                      Resume (PDF)
                    </button>
                    <button
                      type="button"
                      className={`rounded-lg px-3 py-1.5 text-[11px] font-semibold ${
                        tab === "cover"
                          ? "bg-emerald-700 text-white"
                          : "border border-slate-200 text-slate-700"
                      }`}
                      onClick={() => setTabByItem((m) => ({ ...m, [key]: "cover" }))}
                    >
                      Cover Letter (PDF)
                    </button>
                    {(applySt === "ready_to_submit" ||
                      applySt === "filled" ||
                      item.apply?.phase5_done) && (
                      <button
                        type="button"
                        data-testid="cart-fill-review-tab"
                        className={`rounded-lg px-3 py-1.5 text-[11px] font-semibold ${
                          tab === "fill"
                            ? "bg-emerald-700 text-white"
                            : "border border-slate-200 text-slate-700"
                        }`}
                        onClick={() => {
                          setTabByItem((m) => ({ ...m, [key]: "fill" }));
                          if (item.item_id && !fillReviewByItem[item.item_id]) {
                            void loadFillReview(item);
                          }
                        }}
                      >
                        已填内容（可翻阅）
                      </button>
                    )}
                    <button
                      type="button"
                      disabled={busyId === item.item_id || item.status === "confirmed"}
                      data-testid="cart-confirm-pdf-btn"
                      className="ml-auto rounded-lg bg-slate-900 px-3 py-1.5 text-[11px] font-semibold text-white disabled:opacity-40"
                      onClick={() => void onConfirm(item)}
                    >
                      {item.status === "confirmed"
                        ? "已保存到文件夹"
                        : busyId === item.item_id
                          ? "写入文件夹…"
                          : "确认最终版 → 存入文件夹"}
                    </button>
                  </div>
                  {(item.rewrite_ms != null || item.cover_letter_ms != null) && (
                    <p className="mb-2 text-[11px] text-slate-500">
                      计时：rewrite {formatSeconds(item.rewrite_ms)}
                      {item.cover_letter_ms != null
                        ? ` · cover ${formatSeconds(item.cover_letter_ms)}`
                        : ""}
                      {item.elapsed_ms != null ? ` · 合计 ${formatSeconds(item.elapsed_ms)}` : ""}
                    </p>
                  )}
                  {tab === "fill" ? (
                    <div className="space-y-3" data-testid="cart-fill-review">
                      {fillLoadingId === item.item_id ? (
                        <p className="text-xs text-slate-500">加载填表快照…</p>
                      ) : null}
                      {(() => {
                        const review = item.item_id ? fillReviewByItem[item.item_id] : undefined;
                        const step = (item.item_id && fillStepByItem[item.item_id]) || "profile";
                        const stepIdx = FILL_REVIEW_STEPS.findIndex((s) => s.id === step);
                        const payload = review?.review;
                        const checklist = payload?.profile_checklist || item.apply?.profile_checklist || [];
                        const filled = payload?.filled_fields || item.apply?.filled_fields || [];
                        const rows =
                          step === "profile" ? checklist : step === "filled" ? filled : [];
                        return (
                          <>
                            <div className="flex flex-wrap gap-1.5">
                              {FILL_REVIEW_STEPS.map((s) => (
                                <button
                                  key={s.id}
                                  type="button"
                                  className={`rounded-lg px-2.5 py-1 text-[11px] font-semibold ${
                                    step === s.id
                                      ? "bg-[#14352b] text-white"
                                      : "border border-slate-200 text-slate-700"
                                  }`}
                                  onClick={() =>
                                    item.item_id &&
                                    setFillStepByItem((m) => ({ ...m, [item.item_id!]: s.id }))
                                  }
                                >
                                  {s.label}
                                </button>
                              ))}
                            </div>
                            <p className="text-[11px] text-slate-500">
                              {FILL_REVIEW_STEPS[stepIdx]?.hint}
                              {payload?.dry_run ? " · dry-run（未打生产站）" : ""}
                              {payload?.paused_before_submit !== false
                                ? " · Submit 未点击"
                                : ""}
                            </p>
                            <div className="flex items-center gap-2">
                              <button
                                type="button"
                                className="rounded-lg border border-slate-200 px-3 py-1 text-[11px] font-semibold disabled:opacity-40"
                                disabled={stepIdx <= 0}
                                onClick={() => {
                                  if (!item.item_id || stepIdx <= 0) return;
                                  setFillStepByItem((m) => ({
                                    ...m,
                                    [item.item_id!]: FILL_REVIEW_STEPS[stepIdx - 1].id,
                                  }));
                                }}
                              >
                                ← 上一步
                              </button>
                              <button
                                type="button"
                                className="rounded-lg border border-slate-200 px-3 py-1 text-[11px] font-semibold disabled:opacity-40"
                                disabled={stepIdx >= FILL_REVIEW_STEPS.length - 1}
                                onClick={() => {
                                  if (!item.item_id || stepIdx >= FILL_REVIEW_STEPS.length - 1) return;
                                  setFillStepByItem((m) => ({
                                    ...m,
                                    [item.item_id!]: FILL_REVIEW_STEPS[stepIdx + 1].id,
                                  }));
                                }}
                              >
                                下一步 →
                              </button>
                              {!review && item.item_id ? (
                                <button
                                  type="button"
                                  className="ml-auto text-[11px] font-semibold text-emerald-800 underline"
                                  onClick={() => void loadFillReview(item)}
                                >
                                  刷新快照
                                </button>
                              ) : null}
                            </div>
                            {step === "screenshot" ? (
                              cart?.cart_id && item.item_id && (payload?.screenshot_path || item.apply?.screenshot_path) ? (
                                // eslint-disable-next-line @next/next/no-img-element
                                <img
                                  src={getShoppingCartFillScreenshotUrl(
                                    cart.cart_id,
                                    item.item_id,
                                    userId
                                  )}
                                  alt="ATS fill screenshot"
                                  className="max-h-[60vh] w-full rounded-xl border border-slate-200 object-contain bg-slate-50"
                                  data-testid="cart-fill-screenshot"
                                />
                              ) : (
                                <p className="rounded-xl border border-dashed border-slate-200 bg-slate-50 px-3 py-6 text-center text-xs text-slate-500">
                                  暂无截图（dry-run 或填表未产出截图）
                                </p>
                              )
                            ) : null}
                            {step === "pause" ? (
                              <div className="rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-xs text-amber-950">
                                <p className="font-semibold">已停在 Submit 前</p>
                                <p className="mt-1">
                                  注册/登录与表单填写已完成，最终「一键提交」在阶段 6。
                                  点「查看表单」可跳到官网已填好的 Submit 页（本机浏览器恢复会话）。
                                </p>
                                <button
                                  type="button"
                                  data-testid="cart-open-form-btn-pause"
                                  disabled={openFormBusyId === item.item_id}
                                  className="mt-3 rounded-lg bg-[#14352b] px-3 py-1.5 text-[11px] font-semibold text-white disabled:opacity-40"
                                  onClick={() => void openFilledForm(item)}
                                >
                                  {openFormBusyId === item.item_id
                                    ? "打开中…"
                                    : "查看表单 → 官网 Submit 页"}
                                </button>
                              </div>
                            ) : null}
                            {(step === "profile" || step === "filled") && (
                              <div className="max-h-[52vh] space-y-2 overflow-auto rounded-xl border border-slate-200 bg-[#f7f8f6] p-3">
                                {rows.length ? (
                                  rows.map((row, i) => (
                                    <div
                                      key={`${row.field}-${i}`}
                                      className="grid grid-cols-[140px_1fr_auto] gap-2 border-b border-slate-200/70 pb-2 text-[12px] last:border-0"
                                    >
                                      <span className="font-semibold text-slate-700">
                                        {row.field || "—"}
                                      </span>
                                      <span className="break-all text-slate-800">
                                        {row.value || "（空）"}
                                      </span>
                                      <span className="text-[10px] font-semibold uppercase text-slate-500">
                                        {row.tier || row.status || ""}
                                      </span>
                                    </div>
                                  ))
                                ) : (
                                  <p className="text-xs text-slate-500">暂无字段 — 点「刷新快照」或先完成投递填表。</p>
                                )}
                              </div>
                            )}
                          </>
                        );
                      })()}
                    </div>
                  ) : (
                    <>
                      <p className="mb-2 text-[11px] text-slate-500">
                        {item.status === "confirmed"
                          ? `已确认：下方为文件夹中的最终 PDF${item.folder ? ` · ${item.folder}` : ""}。`
                          : "预览 PDF（仅浏览器展示，确认后才写入 data/shopping_cart/…）。"}
                      </p>
                      <iframe
                        key={`${item.item_id}-${tab}-${item.status}`}
                        title={`${tab} PDF preview`}
                        src={getShoppingCartItemPreviewUrl(
                          cart.cart_id,
                          item.item_id,
                          userId,
                          tab === "cover" ? "cover" : "resume"
                        )}
                        className="h-[min(70vh,820px)] w-full rounded-xl border border-slate-200 bg-slate-100"
                        data-testid="cart-pdf-preview"
                      />
                    </>
                  )}
                </div>
              ) : null}

              {open && item.status === "failed" && hasResult ? (
                <div className="border-t border-slate-100 px-4 py-3 text-xs text-rose-700">
                  生成失败：{item.error || "unknown"}
                </div>
              ) : null}
              {open &&
              (item.status === "generating" || item.status === "stalled") &&
              hasResult ? (
                <div className="border-t border-slate-100 px-4 py-3 text-xs text-amber-800">
                  {item.status === "stalled"
                    ? item.error || "生成较慢，仍在后台进行；可先处理其它已完成职位。"
                    : "正在生成简历与 Cover Letter，完成后可预览/投递。"}
                </div>
              ) : null}
            </div>
          );
        })}
      </section>

      {!hasResult ? (
        <div
          className="fixed bottom-0 left-0 right-0 z-30 border-t border-slate-200 bg-white/95 backdrop-blur"
          data-testid="shopping-cart-batch-bar"
        >
          <div className="mx-auto flex max-w-4xl flex-wrap items-center justify-between gap-3 px-4 py-3">
            <div className="text-sm text-slate-700">
              已选 <strong className="text-emerald-700">{pendingCount || internJobIds.length}</strong>{" "}
              个职位
            </div>
            <button
              type="button"
              disabled={!canRefine}
              data-testid="batch-refine-btn"
              className="rounded-xl bg-emerald-700 px-5 py-2.5 text-sm font-semibold text-white disabled:opacity-40"
              onClick={() => void runGenerate()}
            >
              {refining ? "Refine 进行中…" : "批量 Refine"}
            </button>
          </div>
        </div>
      ) : null}
    </div>
  );
}
