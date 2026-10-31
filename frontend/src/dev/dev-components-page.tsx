import { useState } from "react";
import { useTranslation } from "react-i18next";
import {
  type Box,
  PageCanvas,
  type PageCanvasMode,
  type Region,
} from "@/components/page-canvas/PageCanvas";
import { QmdEditor } from "@/components/qmd/QmdEditor";
import { QmdRenderer } from "@/components/qmd/QmdRenderer";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import samplePageUrl from "@/dev/sample-page.png";

const SAMPLE_MCQ_STEM =
  "إِذَا كَانَتْ الدَّالَّةُ $f(x) = x^2 - 4x + 4$، فَمَا قِيمَةُ $x$ الَّتِي تَجْعَلُ $f(x) = 0$؟";

const SAMPLE_MCQ_CHOICES = [
  { label: "أ", content: "$x = 2$" },
  { label: "ب", content: "$x = -2$" },
  { label: "ج", content: "$x = \\sqrt{2}$" },
  { label: "د", content: "$x = 0$" },
];

const SAMPLE_CHEMISTRY =
  "تَفَاعُلُ تَكْوِينِ الْمَاءِ: $$\\ce{2H2(g) + O2(g) ->[\\Delta] 2H2O(l)}$$ وَأَيْضًا أَيُونُ الْكَبْرِيتَاتِ $\\ce{SO4^2-}$.";

const SAMPLE_TABLE = `| العنصر | الرمز | العدد الذري |
| --- | --- | --- |
| الهيدروجين | $\\ce{H}$ | 1 |
| الأكسجين | $\\ce{O}$ | 8 |
| الكربون | $\\ce{C}$ | 6 |`;

const SAMPLE_BLANK =
  "أَكْمِلْ: عَاصِمَةُ جُمْهُورِيَّةِ مِصْرَ الْعَرَبِيَّةِ هِيَ ______ وَتَقَعُ عَلَى نَهْرِ ______.";

const SAMPLE_BROKEN_LATEX =
  "صِيغَةٌ بِهَا خَطَأٌ نَحْوِيٌّ: $\\frac{1 + x}{$ مَعَ نَصٍّ سَلِيمٍ بَعْدَهَا.";

const SAMPLE_ASSETS =
  "صُورَةٌ مُتَاحَةٌ:\n\n![رسم توضيحي للتجربة](asset:fig-available)\n\nوَصُورَةٌ مَفْقُودَةٌ:\n\n![الشكل المقابل](asset:fig-missing-uuid)";

const INITIAL_REGIONS: Region[] = [
  {
    id: "r-heading",
    box: [0.08, 0.05, 0.92, 0.14],
    kind: "heading",
    status: "ok",
    label: "الفصل الأول: الدوال التربيعية",
  },
  {
    id: "r-stimulus",
    box: [0.08, 0.17, 0.92, 0.34],
    kind: "stimulus",
    status: "approved",
    label: "اقرأ الفقرة التالية ثم أجب عن الأسئلة ١–٢",
  },
  {
    id: "r-figure",
    box: [0.55, 0.38, 0.9, 0.62],
    kind: "figure",
    status: "warning",
    label: "شكل ١",
  },
  {
    id: "r-question-1",
    box: [0.08, 0.38, 0.52, 0.66],
    kind: "question",
    status: "ok",
    label: "سؤال ١",
  },
  {
    id: "r-question-2",
    box: [0.08, 0.7, 0.92, 0.92],
    kind: "question",
    status: "error",
    label: "سؤال ٢",
  },
];

function resolveSampleAsset(id: string): string | undefined {
  if (id === "fig-available") {
    return samplePageUrl;
  }
  return undefined;
}

export function DevComponentsPage() {
  const { t, i18n } = useTranslation();
  const currentLang = i18n.language.startsWith("en") ? "en" : "ar";

  const [editorValue, setEditorValue] = useState(
    `${SAMPLE_MCQ_STEM}\n\n${SAMPLE_CHEMISTRY}\n\n${SAMPLE_BLANK}`,
  );
  const [regions, setRegions] = useState<Region[]>(INITIAL_REGIONS);
  const [selectedId, setSelectedId] = useState<string>("r-question-1");
  const [mode, setMode] = useState<PageCanvasMode>("edit");

  const handleRegionChange = (id: string, nextBox: Box) => {
    setRegions((prev) =>
      prev.map((region) =>
        region.id === id ? { ...region, box: nextBox } : region,
      ),
    );
  };

  const handleRegionCreate = (newBox: Box) => {
    const newId = `r-new-${String(regions.length + 1)}`;
    const created: Region = {
      id: newId,
      box: newBox,
      kind: "question",
      status: "ok",
      label: `سؤال ${String(regions.length + 1)}`,
    };
    setRegions((prev) => [...prev, created]);
    setSelectedId(newId);
  };

  return (
    <div className="flex flex-col gap-8">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">{t("dev.title")}</h1>
        <p className="text-muted-foreground mt-1 text-sm">
          {t("dev.subtitle")}
        </p>
      </div>

      {/* 1. QmdRenderer Section */}
      <section className="flex flex-col gap-4">
        <h2 className="text-lg font-semibold">{t("dev.rendererSection")}</h2>
        <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
          <Card>
            <CardHeader>
              <CardTitle className="text-sm">{t("dev.sampleMcq")}</CardTitle>
            </CardHeader>
            <CardContent className="flex flex-col gap-3">
              <QmdRenderer source={SAMPLE_MCQ_STEM} lang={currentLang} />
              <div className="grid grid-cols-2 gap-2">
                {SAMPLE_MCQ_CHOICES.map((choice) => (
                  <div
                    key={choice.label}
                    className="border-border flex items-center gap-2 rounded-md border px-3 py-1.5"
                  >
                    <span className="font-semibold">{choice.label})</span>
                    <QmdRenderer
                      source={choice.content}
                      lang={currentLang}
                      inline
                    />
                  </div>
                ))}
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle className="text-sm">
                {t("dev.sampleChemistry")}
              </CardTitle>
            </CardHeader>
            <CardContent>
              <QmdRenderer source={SAMPLE_CHEMISTRY} lang={currentLang} />
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle className="text-sm">{t("dev.sampleTable")}</CardTitle>
            </CardHeader>
            <CardContent>
              <QmdRenderer source={SAMPLE_TABLE} lang={currentLang} />
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle className="text-sm">{t("dev.sampleBlank")}</CardTitle>
            </CardHeader>
            <CardContent>
              <QmdRenderer source={SAMPLE_BLANK} lang={currentLang} />
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle className="text-sm">
                {t("dev.sampleBrokenLatex")}
              </CardTitle>
            </CardHeader>
            <CardContent>
              <QmdRenderer source={SAMPLE_BROKEN_LATEX} lang={currentLang} />
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle className="text-sm">
                {t("dev.sampleMissingAsset")}
              </CardTitle>
            </CardHeader>
            <CardContent>
              <QmdRenderer
                source={SAMPLE_ASSETS}
                resolveAsset={resolveSampleAsset}
                lang={currentLang}
              />
            </CardContent>
          </Card>
        </div>
      </section>

      {/* 2. QmdEditor Section */}
      <section className="flex flex-col gap-4">
        <h2 className="text-lg font-semibold">{t("dev.editorSection")}</h2>
        <Card>
          <CardContent className="pt-6">
            <QmdEditor
              value={editorValue}
              onChange={setEditorValue}
              lang={currentLang}
              resolveAsset={resolveSampleAsset}
            />
          </CardContent>
        </Card>
      </section>

      {/* 3. PageCanvas Section */}
      <section className="flex flex-col gap-4">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h2 className="text-lg font-semibold">{t("dev.canvasSection")}</h2>
          <div className="flex items-center gap-1.5">
            {(["view", "edit", "draw"] as const).map((m) => (
              <Button
                key={m}
                type="button"
                size="sm"
                variant={mode === m ? "default" : "outline"}
                onClick={() => {
                  setMode(m);
                }}
              >
                {m === "view"
                  ? t("dev.modeView")
                  : m === "edit"
                    ? t("dev.modeEdit")
                    : t("dev.modeDraw")}
              </Button>
            ))}
          </div>
        </div>

        <PageCanvas
          src={samplePageUrl}
          width={560}
          height={784}
          regions={regions}
          selectedId={selectedId}
          onSelect={setSelectedId}
          mode={mode}
          onChange={handleRegionChange}
          onCreate={handleRegionCreate}
          className="h-[640px]"
        />
      </section>
    </div>
  );
}
