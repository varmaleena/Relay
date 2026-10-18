import i18n from "i18next";
import { initReactI18next } from "react-i18next";
import en from "../locales/en.json";
import hi from "../locales/hi.json";
const stored = localStorage.getItem("relay.language");
void i18n.use(initReactI18next).init({
  resources: { en: { translation: en }, hi: { translation: hi } },
  lng: stored === "hi" ? "hi" : "en",
  fallbackLng: "en",
  interpolation: { escapeValue: false },
  returnNull: false,
});
i18n.on("languageChanged", (lang) => {
  document.documentElement.lang = lang;
  localStorage.setItem("relay.language", lang);
});
document.documentElement.lang = i18n.language;
export default i18n;
