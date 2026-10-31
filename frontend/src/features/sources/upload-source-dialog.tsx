import { AlertCircle, FileUp } from "lucide-react";
import {
  type ChangeEvent,
  type DragEvent,
  type SyntheticEvent,
  useRef,
  useState,
} from "react";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router";
import { ApiError } from "@/api/client";
import { useUploadSource } from "@/api/hooks/sources";
import { useSubjects } from "@/api/hooks/subjects";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { stripFileExtension } from "@/lib/format";
import { cn } from "@/lib/utils";

export const MAX_UPLOAD_BYTES = 300 * 1024 * 1024; // 300 MB

type UploadErrorKey =
  | "fileRequired"
  | "subjectRequired"
  | "titleRequired"
  | "invalidType"
  | "fileTooLarge"
  | "invalidPdf"
  | "uploadFailed";

function validateWorkbookFile(file: File): UploadErrorKey | null {
  const isPdfType = file.type === "application/pdf";
  const isPdfExt = file.name.toLowerCase().endsWith(".pdf");
  if (!isPdfType && !isPdfExt) {
    return "invalidType";
  }
  if (file.size > MAX_UPLOAD_BYTES) {
    return "fileTooLarge";
  }
  return null;
}

export interface UploadSourceDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function UploadSourceDialog({
  open,
  onOpenChange,
}: UploadSourceDialogProps) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const { data: subjectsData } = useSubjects();
  const uploadMutation = useUploadSource();

  const subjects = Array.isArray(subjectsData?.items) ? subjectsData.items : [];

  const [subjectId, setSubjectId] = useState("");
  const [title, setTitle] = useState("");
  const [titleEdited, setTitleEdited] = useState(false);
  const [grade, setGrade] = useState("");
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [errorKey, setErrorKey] = useState<UploadErrorKey | null>(null);
  const [progress, setProgress] = useState<number>(0);
  const [isDragging, setIsDragging] = useState(false);

  const fileInputRef = useRef<HTMLInputElement | null>(null);

  const effectiveSubjectId = subjectId || (subjects[0]?.id ?? "");
  const isUploading = uploadMutation.isPending;

  const resetForm = () => {
    setSubjectId("");
    setTitle("");
    setTitleEdited(false);
    setGrade("");
    setSelectedFile(null);
    setErrorKey(null);
    setProgress(0);
    setIsDragging(false);
  };

  const handleOpenChange = (nextOpen: boolean) => {
    if (!nextOpen) {
      resetForm();
    }
    onOpenChange(nextOpen);
  };

  const handleFileSelected = (file: File | undefined) => {
    if (!file) {
      return;
    }
    setSelectedFile(file);
    if (!titleEdited || title.trim().length === 0) {
      setTitle(stripFileExtension(file.name));
    }
    const validationError = validateWorkbookFile(file);
    setErrorKey(validationError);
  };

  const handleFileInputChange = (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    handleFileSelected(file);
  };

  const handleDrop = (event: DragEvent<HTMLDivElement>) => {
    event.preventDefault();
    setIsDragging(false);
    const file = event.dataTransfer.files[0];
    handleFileSelected(file);
  };

  const handleSubmit = async (event: SyntheticEvent<HTMLFormElement>) => {
    event.preventDefault();

    if (!selectedFile) {
      setErrorKey("fileRequired");
      return;
    }

    const fileError = validateWorkbookFile(selectedFile);
    if (fileError) {
      setErrorKey(fileError);
      return;
    }

    if (!effectiveSubjectId) {
      setErrorKey("subjectRequired");
      return;
    }

    const resolvedTitle = title.trim() || stripFileExtension(selectedFile.name);
    if (!resolvedTitle) {
      setErrorKey("titleRequired");
      return;
    }

    setErrorKey(null);
    setProgress(0);

    try {
      const result = await uploadMutation.mutateAsync({
        file: selectedFile,
        subject_id: effectiveSubjectId,
        title: resolvedTitle,
        grade: grade.trim() || undefined,
        onProgress: setProgress,
      });
      handleOpenChange(false);
      await navigate(`/sources/${result.source.id}`);
    } catch (err) {
      if (err instanceof ApiError) {
        if (err.code === "invalid_pdf") {
          setErrorKey("invalidPdf");
          return;
        }
        if (err.code === "file_too_large") {
          setErrorKey("fileTooLarge");
          return;
        }
      }
      setErrorKey("uploadFailed");
    }
  };

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{t("sources.upload.dialogTitle")}</DialogTitle>
          <DialogDescription>
            {t("sources.upload.dialogDescription")}
          </DialogDescription>
        </DialogHeader>

        <form
          noValidate
          onSubmit={(event) => {
            void handleSubmit(event);
          }}
          className="mt-2 flex flex-col gap-4"
        >
          {errorKey ? (
            <div
              role="alert"
              aria-live="assertive"
              data-testid="upload-error"
              className="border-destructive/30 bg-destructive/10 text-destructive flex items-center gap-2 rounded-md border px-3 py-2 text-sm"
            >
              <AlertCircle className="size-4 shrink-0" aria-hidden="true" />
              <span>{t(`sources.upload.errors.${errorKey}`)}</span>
            </div>
          ) : null}

          <div className="flex flex-col gap-1.5">
            <Label htmlFor="upload-file">{t("sources.upload.fileLabel")}</Label>
            <div
              onDragOver={(event) => {
                event.preventDefault();
                setIsDragging(true);
              }}
              onDragLeave={() => {
                setIsDragging(false);
              }}
              onDrop={handleDrop}
              onClick={() => {
                fileInputRef.current?.click();
              }}
              onKeyDown={(event) => {
                if (event.key === "Enter" || event.key === " ") {
                  event.preventDefault();
                  fileInputRef.current?.click();
                }
              }}
              role="button"
              tabIndex={0}
              aria-label={t("sources.upload.dropzonePrompt")}
              data-testid="upload-dropzone"
              className={cn(
                "border-border hover:border-primary/60 hover:bg-muted/40 flex cursor-pointer flex-col items-center justify-center gap-1.5 rounded-lg border-2 border-dashed p-5 text-center transition-colors",
                isDragging && "border-primary bg-primary/5",
              )}
            >
              <FileUp
                className="text-muted-foreground size-7"
                aria-hidden="true"
              />
              <span className="text-sm font-medium">
                {t("sources.upload.dropzonePrompt")}
              </span>
              <span className="text-muted-foreground text-xs">
                {t("sources.upload.dropzoneHint")}
              </span>
              {selectedFile ? (
                <span
                  data-testid="selected-file-name"
                  className="text-primary mt-1 text-xs font-medium"
                >
                  {t("sources.upload.selectedFile", {
                    name: selectedFile.name,
                  })}
                </span>
              ) : null}
            </div>
            {/* A sibling of the dropzone, not a child: nesting it would put a form control
                inside role="button", which assistive tech cannot operate. */}
            <input
              ref={fileInputRef}
              id="upload-file"
              type="file"
              data-testid="upload-file-input"
              onChange={handleFileInputChange}
              disabled={isUploading}
              className="sr-only"
            />
          </div>

          <div className="flex flex-col gap-1.5">
            <Label htmlFor="upload-subject">
              {t("sources.upload.subjectLabel")}
            </Label>
            <select
              id="upload-subject"
              value={effectiveSubjectId}
              onChange={(event) => {
                setSubjectId(event.target.value);
              }}
              disabled={isUploading}
              className="border-input bg-background focus-visible:border-ring focus-visible:ring-ring/50 flex h-9 w-full rounded-md border px-3 py-1 text-sm shadow-xs outline-none focus-visible:ring-[3px] disabled:opacity-50"
            >
              <option value="">{t("sources.upload.subjectPlaceholder")}</option>
              {subjects.map((subj) => (
                <option key={subj.id} value={subj.id}>
                  {subj.name}
                </option>
              ))}
            </select>
          </div>

          <div className="flex flex-col gap-1.5">
            <Label htmlFor="upload-title">
              {t("sources.upload.titleLabel")}
            </Label>
            <Input
              id="upload-title"
              type="text"
              value={title}
              placeholder={t("sources.upload.titlePlaceholder")}
              onChange={(event) => {
                setTitle(event.target.value);
                setTitleEdited(true);
              }}
              disabled={isUploading}
            />
          </div>

          <div className="flex flex-col gap-1.5">
            <Label htmlFor="upload-grade">
              {t("sources.upload.gradeLabel")}
            </Label>
            <Input
              id="upload-grade"
              type="text"
              value={grade}
              placeholder={t("sources.upload.gradePlaceholder")}
              onChange={(event) => {
                setGrade(event.target.value);
              }}
              disabled={isUploading}
            />
          </div>

          {isUploading || progress > 0 ? (
            <div aria-live="polite" className="flex flex-col gap-1.5">
              <div className="flex items-center justify-between text-xs">
                <span>{t("sources.upload.progressLabel")}</span>
                <span dir="ltr" className="font-mono tabular-nums">
                  {`${String(progress)}%`}
                </span>
              </div>
              <div
                role="progressbar"
                aria-label={t("sources.upload.progressLabel")}
                aria-valuenow={progress}
                aria-valuemin={0}
                aria-valuemax={100}
                className="bg-muted h-2 w-full overflow-hidden rounded-full"
              >
                <div
                  className="bg-primary h-full transition-all"
                  style={{ width: `${String(progress)}%` }}
                />
              </div>
            </div>
          ) : null}

          <DialogFooter>
            <Button
              type="button"
              variant="outline"
              disabled={isUploading}
              onClick={() => {
                handleOpenChange(false);
              }}
            >
              {t("sources.upload.cancel")}
            </Button>
            <Button
              type="submit"
              disabled={isUploading}
              data-testid="upload-submit"
            >
              {isUploading
                ? t("sources.upload.uploading")
                : t("sources.upload.submit")}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
