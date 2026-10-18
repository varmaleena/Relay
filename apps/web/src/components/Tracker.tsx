import {
  safeGetRetry,
  safeGetRetryDelay,
  safePollInterval,
} from "../lib/polling";
import {
  useInfiniteQuery,
  useMutation,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { Bell, Check } from "lucide-react";
import { api } from "../lib/connection";
import { Progress } from "./Primitives";
import type { CaseView } from "../generated/contracts";
import { friendlyField, routingSetupMissing } from "./Packets";
import InformationResponse from "./InformationResponse";

export default function Tracker({
  view,
  onReview,
}: {
  view: CaseView;
  onReview: (packetId?: string) => void;
}) {
  const { t, i18n } = useTranslation();
  const cache = useQueryClient();
  const packets = useQuery({
    queryKey: ["packets", view.caseId],
    queryFn: () => api.E14({ caseId: view.caseId }),
    refetchInterval: (query) => safePollInterval(query, 15000),
    retry: safeGetRetry,
    retryDelay: safeGetRetryDelay,
  });
  const events = useInfiniteQuery({
    queryKey: ["events", view.caseId],
    initialPageParam: "",
    queryFn: ({ pageParam }) =>
      api.E20({
        caseId: view.caseId,
        query: { limit: 30, ...(pageParam ? { cursor: pageParam } : {}) },
      }),
    getNextPageParam: (page) => page.nextCursor || undefined,
    refetchInterval: (query) =>
      !query.state.error && query.state.data?.pages.length === 1
        ? 15000
        : false,
    retry: safeGetRetry,
    retryDelay: safeGetRetryDelay,
  });
  const notifications = useInfiniteQuery({
    queryKey: ["notifications", view.caseId],
    initialPageParam: "",
    queryFn: ({ pageParam }) =>
      api.E46_notifications({
        caseId: view.caseId,
        query: pageParam ? { cursor: pageParam } : {},
      }),
    getNextPageParam: (page) => page.nextCursor || undefined,
    refetchInterval: (query) =>
      !query.state.error && query.state.data?.pages.length === 1
        ? 15000
        : false,
    retry: safeGetRetry,
    retryDelay: safeGetRetryDelay,
  });
  const eventItems = events.data?.pages.flatMap((page) => page.items) || [];
  const notificationItems =
    notifications.data?.pages.flatMap((page) => page.items) || [];
  const markRead = useMutation({
    mutationFn: (notificationId: string) =>
      api.E47_read({ caseId: view.caseId, notificationId, body: {} }),
    onSuccess: () =>
      void cache.invalidateQueries({
        queryKey: ["notifications", view.caseId],
      }),
  });
  const date = (value: string) =>
    new Intl.DateTimeFormat(i18n.language === "hi" ? "hi-IN" : "en-IN", {
      dateStyle: "medium",
      timeStyle: "short",
    }).format(new Date(value));
  const action = (value: string) => {
    const key = `timelineEvents.${value.replaceAll(".", "_")}`;
    return i18n.exists(key) ? t(key) : t("timelineOther");
  };
  return (
    <section className="tracker-screen" aria-labelledby="tracker-title">
      <div className="panel-head">
        <h2 id="tracker-title">{t("trackerTitle")}</h2>
        <button className="outline" onClick={() => onReview()}>
          {t("messagesTitle")}
        </button>
      </div>
      <p>{t("trackerPurpose")}</p>
      <p className="plan-notice">{t("trackerSimulation")}</p>
      {packets.isPending && <Progress text={t("messagesLoading")} />}
      {(packets.isError || events.isError || notifications.isError) && (
        <p className="error-banner" role="alert">
          {t("trackerLoadFailed")}
          <button
            className="text-button"
            onClick={() => {
              void packets.refetch();
              void events.refetch();
              void notifications.refetch();
            }}
          >
            {t("retry")}
          </button>
        </p>
      )}
      {!packets.isPending && !packets.data?.items.length && (
        <p>{t("messagesEmpty")}</p>
      )}
      <ol className="tracker-stations">
        {packets.data?.items.map((item) => (
          <li key={item.packetId}>
            <div>
              <h3>
                {item.recipientName ||
                  view.plan?.steps.find(
                    (step) => step.recipientId === item.recipientId,
                  )?.recipientName ||
                  item.recipientId}
              </h3>
              <p className="tracker-status">
                {t(`messageStatus.${item.status}`)}
              </p>
              <p>{t("messageVersion", { version: item.version })}</p>
              {item.delivery && (
                <div className="tracker-receipt">
                  <p>
                    {t("messageDelivered", {
                      reference: item.delivery.ticketRef,
                    })}
                  </p>
                  {item.delivery.status && (
                    <p>
                      {t("messageReceiptStatus", {
                        status: item.delivery.status,
                      })}
                    </p>
                  )}
                  {item.delivery.missingItems?.some(routingSetupMissing) && (
                    <p>{t("messageRoutingIncomplete")}</p>
                  )}
                  {!!item.delivery.missingItems?.filter(
                    (key) => !routingSetupMissing(key),
                  ).length && (
                    <p>
                      {t("messageReceiptMissing", {
                        items: item.delivery
                          .missingItems!.filter(
                            (key) => !routingSetupMissing(key),
                          )
                          .map((key) => friendlyField(key, t))
                          .join(", "),
                      })}
                    </p>
                  )}
                </div>
              )}
              {item.stale && (
                <p className="error-banner">{t("messageStale")}</p>
              )}
              <InformationResponse
                view={view}
                item={item}
                onReview={() => onReview(item.packetId)}
              />
            </div>
            <button className="outline" onClick={() => onReview(item.packetId)}>
              {t("trackerReview")}
            </button>
          </li>
        ))}
      </ol>
      <div className="tracker-columns">
        <section aria-labelledby="inbox-title">
          <h3 id="inbox-title">
            <Bell size={21} aria-hidden="true" /> {t("inboxTitle")}
          </h3>
          {!notificationItems.length && <p>{t("inboxEmpty")}</p>}
          <ul className="notification-list">
            {notificationItems.map((item) => (
              <li
                key={item.notificationId}
                className={item.readAt ? "read" : "unread"}
              >
                <p>{item.text}</p>
                <time dateTime={item.createdAt}>{date(item.createdAt)}</time>
                <div className="fact-actions">
                  <button
                    className="text-button"
                    onClick={() => onReview(item.packetId)}
                  >
                    {t("trackerReview")}
                  </button>
                  {!item.readAt && (
                    <button
                      className="outline"
                      disabled={markRead.isPending}
                      onClick={() => markRead.mutate(item.notificationId)}
                    >
                      <Check size={18} aria-hidden="true" />
                      {t("markRead")}
                    </button>
                  )}
                </div>
              </li>
            ))}
          </ul>
          {notifications.hasNextPage && (
            <button
              className="outline"
              disabled={notifications.isFetchingNextPage}
              onClick={() => void notifications.fetchNextPage()}
            >
              {t("updatesMore")}
            </button>
          )}
          {markRead.isError && (
            <p className="error-banner" role="alert">
              {t("error")}
            </p>
          )}
        </section>
        <section aria-labelledby="timeline-title">
          <h3 id="timeline-title">{t("timelineTitle")}</h3>
          {!eventItems.length && <p>{t("timelineEmpty")}</p>}
          <ol className="event-timeline">
            {eventItems.map((event) => (
              <li key={event.eventId}>
                <p>{action(event.action)}</p>
                <time dateTime={event.ts}>{date(event.ts)}</time>
                {event.targetType === "packet" && (
                  <button
                    className="text-button"
                    onClick={() => onReview(event.targetId)}
                  >
                    {t("trackerReview")}
                  </button>
                )}
              </li>
            ))}
          </ol>
          {events.hasNextPage && (
            <button
              className="outline"
              disabled={events.isFetchingNextPage}
              onClick={() => void events.fetchNextPage()}
            >
              {t("updatesMore")}
            </button>
          )}
          {events.data && events.data.pages.length > 1 && (
            <button
              className="text-button"
              onClick={() => {
                void events.refetch();
                void notifications.refetch();
              }}
            >
              {t("updatesRefresh")}
            </button>
          )}
        </section>
      </div>
    </section>
  );
}
