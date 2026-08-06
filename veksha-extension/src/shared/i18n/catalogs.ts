import ar from "./catalogs/i18n_ar.json";
import cs from "./catalogs/i18n_cs.json";
import de from "./catalogs/i18n_de.json";
import el from "./catalogs/i18n_el.json";
import es from "./catalogs/i18n_es.json";
import fi from "./catalogs/i18n_fi.json";
import fr from "./catalogs/i18n_fr.json";
import hi from "./catalogs/i18n_hi.json";
import id from "./catalogs/i18n_id.json";
import it from "./catalogs/i18n_it.json";
import ja from "./catalogs/i18n_ja.json";
import ka from "./catalogs/i18n_ka.json";
import nl from "./catalogs/i18n_nl.json";
import pl from "./catalogs/i18n_pl.json";
import pt from "./catalogs/i18n_pt.json";
import ru from "./catalogs/i18n_ru.json";
import th from "./catalogs/i18n_th.json";
import tr from "./catalogs/i18n_tr.json";
import uk from "./catalogs/i18n_uk.json";
import vi from "./catalogs/i18n_vi.json";
import { EN, type Strings } from "./strings";

const CATALOGS: Record<string, Partial<Strings>> = {
  ar, cs, de, el, es, fi, fr, hi, id, it, ja, ka, nl, pl, pt, ru, th, tr, uk, vi,
};

export function catalogFor(language: string): Strings {
  return { ...EN, ...(CATALOGS[language] ?? {}) };
}
