import { useTranslation } from "react-i18next";
import { Header } from "./Primitives";
import EvalLab, { type EvalReport } from "./EvalLab";
import report from "../data/offline-evaluation.json";

/** Public, immutable synthetic evidence only. No executor or case access. */
export default function ResultsWorkspace() {
  const { t } = useTranslation();
  return (
    <>
      <Header onHome={() => location.assign("/")} />
      <main className="page" id="main">
        <section className="panel" aria-labelledby="release-heading">
          <h1 id="release-heading">{t("evalReleaseTitle")}</h1>
          <p>{t("evalReleaseDate")}</p>
          <p>{t("evalReleaseObserved")}</p>
          <p className="notice">{t("evalReleaseLimit")}</p>
          <details>
            <summary>{t("evalReleaseChecks")}</summary>
            <ul>
              <li>{t("evalReleaseSecurity")}</li>
              <li>{t("evalReleaseReports")}</li>
              <li>{t("evalReleaseCleanup")}</li>
            </ul>
          </details>
          <p>{t("evalReleaseOpen")}</p>
          <a href="/">{t("evalReturnDemo")}</a>
        </section>
        <EvalLab report={report as EvalReport} />
      </main>
    </>
  );
}
