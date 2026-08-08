import { createContext, useContext, useState } from "react";

const translations = {
  en: { name: "English", home: "Home", dashboard: "Dashboard", detect: "Detect", history: "History", analytics: "Analytics", learning: "Learning Center", about: "About", contact: "Contact", admin: "Admin", login: "Login", register: "Register", logout: "Logout", getStarted: "Get Started", learnMore: "Learn More" },
  es: { name: "Español", home: "Inicio", dashboard: "Panel", detect: "Detectar", history: "Historial", analytics: "Análisis", learning: "Centro de aprendizaje", about: "Acerca", contact: "Contacto", admin: "Admin", login: "Entrar", register: "Registrarse", logout: "Salir", getStarted: "Empezar", learnMore: "Saber más" },
  hi: { name: "हिन्दी", home: "होम", dashboard: "डैशबोर्ड", detect: "जाँच करें", history: "इतिहास", analytics: "विश्लेषण", learning: "सीखें", about: "परियोजना", contact: "संपर्क", admin: "एडमिन", login: "लॉगिन", register: "पंजीकरण", logout: "लॉगआउट", getStarted: "शुरू करें", learnMore: "और जानें" },
  fr: { name: "Français", home: "Accueil", dashboard: "Tableau de bord", detect: "Détecter", history: "Historique", analytics: "Analytique", learning: "Centre d'apprentissage", about: "À propos", contact: "Contact", admin: "Admin", login: "Connexion", register: "S'inscrire", logout: "Déconnexion", getStarted: "Commencer", learnMore: "En savoir plus" },
};

const LanguageContext = createContext({});

export function LanguageProvider({ children }) {
  const [lang, setLang] = useState(() => localStorage.getItem("deepguard-lang") || "en");
  const t = (key) => translations[lang]?.[key] ?? translations.en[key] ?? key;

  const changeLanguage = (code) => {
    setLang(code);
    localStorage.setItem("deepguard-lang", code);
  };

  return (
    <LanguageContext.Provider value={{ lang, setLang: changeLanguage, t, languages: translations }}>
      {children}
    </LanguageContext.Provider>
  );
}

export const useLanguage = () => useContext(LanguageContext);
