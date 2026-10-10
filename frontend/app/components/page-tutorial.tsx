"use client";

import { useId, useSyncExternalStore } from "react";
import { usePathname } from "next/navigation";

type Tutorial = {
  page: string;
  purpose: string;
  steps: Array<{ title: string; text: string }>;
  remember: string;
};

const tutorials: Record<string, Tutorial> = {
  "/": {
    page: "Veille",
    purpose: "Cette page rassemble les publications collectées et les faits qui en ont été extraits. Elle vous aide à repérer les informations à examiner.",
    steps: [
      { title: "Parcourez les informations", text: "Les publications sont des documents d’origine. Les événements sont des faits extraits à vérifier dans ces documents." },
      { title: "Vérifiez la source", text: "Ouvrez « Sources et preuves » sous un événement, ou cliquez sur une publication pour consulter son document et sa date." },
      { title: "Étudiez un titre", text: "Passez à « Analyser » pour consulter le dossier d’une action suivie. Les boutons Précédent et Suivant donnent accès aux autres informations." },
    ],
    remember: "Une collecte réussie signifie que des informations ont été récupérées. Elle ne garantit ni une couverture complète ni l’exactitude de chaque fait extrait.",
  },
  "/analysis": {
    page: "Analyser",
    purpose: "Cette page réunit les informations disponibles pour étudier une action : faits, résultats, risques et données nécessaires à sa valorisation.",
    steps: [
      { title: "Choisissez un dossier", text: "Dans « À examiner », ouvrez la fiche documentaire d’un titre. Vous pouvez aussi choisir un titre suivi dans les autres sections." },
      { title: "Lisez les éléments disponibles", text: "« Synthèse » rassemble les points à examiner et les données manquantes. « Résultats » montre les chiffres publiés et leurs évolutions comparables." },
      { title: "Approfondissez l’analyse", text: "« Valorisation » rapporte le prix aux bénéfices annuels lorsque les preuves sont suffisantes. « Documents et faits » permet de retrouver les sources." },
    ],
    remember: "Le score indique une priorité de recherche, pas une recommandation d’achat. Un bénéfice positif ne prouve pas qu’une action est bon marché ; un calcul bloqué signale des données insuffisantes ou incompatibles.",
  },
  "/calendar": {
    page: "Calendrier",
    purpose: "Cette page permet de suivre les dates prévues de résultats d’une société, les estimations et les chiffres publiés conservés pour un titre.",
    steps: [
      { title: "Choisissez une action", text: "Sélectionnez un titre suivi pour afficher son calendrier et l’historique de ses observations." },
      { title: "Consultez le calendrier", text: "Le bouton « Consulter le calendrier » interroge le fournisseur si la cotation et le quota le permettent. Les observations précédentes sont conservées." },
      { title: "Distinguez prévision et résultat", text: "Une date prévue annonce un rendez-vous. Une estimation de bénéfice par action (BPA) est une prévision ; un BPA publié est un chiffre déclaré avec sa source." },
    ],
    remember: "Les dates prévues doivent être confirmées dans une publication officielle. Une date passée ne prouve pas que les résultats sont sortis. Consulter le fournisseur peut utiliser le quota de données disponible.",
  },
  "/portfolio": {
    page: "Portefeuille",
    purpose: "Cette page sert à suivre un portefeuille fictif et à gérer les actions que vous souhaitez observer. Elle ne transmet aucun ordre réel.",
    steps: [
      { title: "Ouvrez une simulation", text: "Dans « Ma simulation », choisissez un portefeuille pour voir le capital disponible, les positions et l’historique. Utilisez « Nouvelle simulation » si vous n’en avez pas." },
      { title: "Gérez les titres suivis", text: "Dans « Titres suivis », ajoutez le symbole boursier d’une action (ticker) et consultez ses cours. Ajouter un titre à cette liste ne signifie pas l’acheter." },
      { title: "Comprenez les opérations", text: "Un achat ou une vente simulés modifient uniquement ce portefeuille fictif. « Univers WLS » présente la liste fournie et les correspondances de cotation disponibles." },
    ],
    remember: "La liste WLS fournie est partielle et non datée : le mode provisoire ne certifie pas l’éligibilité actuelle au challenge. Les cours manquants ou trop anciens peuvent empêcher une opération ou une valorisation complète.",
  },
  "/coverage": {
    page: "Qualité des données",
    purpose: "Cette page explique pourquoi certaines analyses ou simulations ne sont pas encore possibles et indique les informations à compléter.",
    steps: [
      { title: "Repérez les manques", text: "Les compteurs montrent les problèmes rencontrés : cours absent, taux manquant, WLS non vérifié ou preuves de valorisation insuffisantes." },
      { title: "Filtrez les titres", text: "Cliquez sur un compteur, utilisez « Données à compléter » ou recherchez le nom d’un titre. Un même titre peut avoir plusieurs données manquantes." },
      { title: "Préparez les justificatifs", text: "« Préparer les preuves de valorisation » détaille les informations nécessaires. Les formulaires avancés permettent de fournir des correspondances et observations sourcées." },
    ],
    remember: "Une donnée absente ne vaut pas zéro. Saisir une preuve ne la certifie pas : sa cohérence est contrôlée et les informations doivent concerner le titre et sa cotation exacts.",
  },
  "/international": {
    page: "International",
    purpose: "Cette page permet de suivre des actions cotées hors des États-Unis et de comprendre leur valeur en dollars à partir de cours et de taux datés.",
    steps: [
      { title: "Consultez vos cotations", text: "« Mes cotations » affiche les titres internationaux suivis, leurs cours disponibles et leur équivalent en dollars. Un même titre peut avoir plusieurs cotations." },
      { title: "Identifiez une cotation", text: "Dans « Ajouter une cotation », fournissez les identifiants exacts de votre source : symbole local, place de marché, identifiant du titre et devise." },
      { title: "Complétez les cours et taux", text: "« Cours et taux » présente la collecte des taux de référence et permet de fournir une clôture locale ou un taux complémentaire, avec date et source." },
    ],
    remember: "Convertir la valeur d’une action en dollars n’est pas une opération Forex. Les taux de référence BCE peuvent différer de ceux de Bloomberg ; une identité internationale ne prouve pas l’appartenance au WLS.",
  },
};

const storageKey = "market-ai:tutorials:v1";
const changeEvent = "market-ai:tutorials-changed";
let temporaryPreference: boolean | null = null;

function getVisibility() {
  if (temporaryPreference !== null) return temporaryPreference;
  try { return window.localStorage.getItem(storageKey) !== "hidden"; }
  catch { return true; }
}

function subscribe(onChange: () => void) {
  function onStorage(event: StorageEvent) {
    if (event.key === storageKey || event.key === null) { temporaryPreference = null; onChange(); }
  }
  window.addEventListener(changeEvent, onChange);
  window.addEventListener("storage", onStorage);
  return () => {
    window.removeEventListener(changeEvent, onChange);
    window.removeEventListener("storage", onStorage);
  };
}

function setVisibility(visible: boolean) {
  temporaryPreference = visible;
  try { window.localStorage.setItem(storageKey, visible ? "visible" : "hidden"); temporaryPreference = null; }
  catch { /* The toggle still works for this visit when browser storage is unavailable. */ }
  window.dispatchEvent(new Event(changeEvent));
}

export function PageTutorial() {
  const pathname = usePathname();
  const id = useId();
  const visible = useSyncExternalStore(subscribe, getVisibility, () => true);
  const tutorial = tutorials[pathname];
  if (!tutorial) return null;
  return <section className="tutorial-panel" aria-label={`Tutoriel : ${tutorial.page}`}>
    <div className="flex flex-wrap items-center justify-between gap-3">
      <h2 className="text-sm font-semibold text-white"><span className="mr-2 text-signal" aria-hidden="true">?</span>Mode d’emploi · {tutorial.page}</h2>
      <button type="button" aria-expanded={visible} aria-controls={`${id}-content`} onClick={() => setVisibility(!visible)} className="tutorial-toggle">
        {visible ? "Masquer le tutoriel" : "Afficher le tutoriel"}
      </button>
    </div>
    <div id={`${id}-content`} hidden={!visible}>
      <p className="mb-4 mt-3 max-w-3xl text-sm leading-6 text-slate-300">{tutorial.purpose}</p>
      <ol className="grid gap-4 md:grid-cols-3">{tutorial.steps.map((step, index) => <li key={step.title} className="flex gap-3">
        <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-signal/10 text-xs font-semibold text-signal" aria-hidden="true">{index + 1}</span>
        <div className="min-w-0"><h3 className="text-sm font-medium text-white">{step.title}</h3><p className="mt-1 text-xs leading-5 text-slate-400">{step.text}</p></div>
      </li>)}</ol>
      <p className="mt-4 border-t border-white/10 pt-3 text-xs leading-5 text-slate-400"><span className="font-medium text-slate-200">À retenir : </span>{tutorial.remember}</p>
      <p className="mt-2 text-xs text-slate-400">Votre choix d’affichage s’applique à toutes les pages et est mémorisé dans ce navigateur lorsque le stockage est disponible.</p>
    </div>
  </section>;
}
