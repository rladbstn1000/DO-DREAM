package A704.DODREAM.file.service;

import java.io.File;
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.util.UUID;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;
import org.springframework.web.multipart.MultipartFile;

import lombok.extern.slf4j.Slf4j;

@Slf4j
@Service
public class FileStorageService {

	private final Path uploadPath;
	private final Path tempPath;

	public FileStorageService(
		@Value("${file.upload.dir}") String uploadDir,
		@Value("${file.upload.temp-dir}") String tempDir) throws IOException {
		this.uploadPath = Paths.get(uploadDir).toAbsolutePath().normalize();
		this.tempPath = Paths.get(tempDir).toAbsolutePath().normalize();

		// 디렉토리 생성
		Files.createDirectories(this.uploadPath);
		Files.createDirectories(this.tempPath);

		log.info("File upload directory: {}", this.uploadPath);
		log.info("File temp directory: {}", this.tempPath);
	}

	/**
	 * PDF 파일 저장
	 */
	public String storeFile(MultipartFile file) throws IOException {
        PdfInputPolicy.filename(file.getOriginalFilename());
        if (!"application/pdf".equals(file.getContentType())) throw new IllegalArgumentException("Expected PDF media type");
        String storedFileName = UUID.randomUUID() + ".pdf";
        byte[] bytes;
        try (var input=file.getInputStream()) { bytes=PdfInputPolicy.read(input,file.getSize()); }
        Files.write(safeLeaf(this.uploadPath,storedFileName),bytes,java.nio.file.StandardOpenOption.CREATE_NEW);
        log.info("PDF stored as {}",storedFileName);
		return storedFileName;
	}

	/**
	 * 임시 파일 저장 (이미지 변환 중간 파일)
	 */
	public File saveTempFile(byte[] imageData, String prefix, String extension) throws IOException {
        if (prefix == null || !prefix.matches("[A-Za-z0-9_-]{1,64}") || extension == null
            || !extension.matches("[a-z0-9]{1,8}") || imageData == null || imageData.length > PdfInputPolicy.MAX_BYTES)
            throw new IllegalArgumentException("Invalid temporary image input");
        String fileName = prefix + "_" + UUID.randomUUID() + "." + extension;
		Path tempFilePath = safeLeaf(this.tempPath,fileName);
		Files.write(tempFilePath, imageData, java.nio.file.StandardOpenOption.CREATE_NEW);

		File tempFile = tempFilePath.toFile();
		tempFile.deleteOnExit(); // JVM 종료 시 자동 삭제

		return tempFile;
	}

	/**
	 * 파일 경로 가져오기
	 */
	public Path getFilePath(String fileName) {
		return safeLeaf(this.uploadPath,fileName);
	}

	/**
	 * 파일 삭제
	 */
	public void deleteFile(String fileName) throws IOException {
		Path filePath = safeLeaf(this.uploadPath,fileName);
		Files.deleteIfExists(filePath);
		log.info("File deleted: {}", fileName);
	}

	/**
	 * 임시 파일 삭제
	 */
	public void deleteTempFile(File file) {
        if (file != null && file.exists()) {
            Path expected=safeLeaf(this.tempPath,file.getName());
            if (!expected.equals(file.toPath().toAbsolutePath().normalize())) throw new IllegalArgumentException("Outside temporary directory");
            boolean deleted = expected.toFile().delete();
			if (deleted) {
				log.debug("Temp file deleted: {}", file.getName());
			}
		}
	}

    private Path safeLeaf(Path root, String name) {
        if (name == null || name.isBlank() || name.contains("/") || name.contains("\\")
            || name.equals(".") || name.equals("..") || name.codePoints().anyMatch(Character::isISOControl))
            throw new IllegalArgumentException("Invalid stored filename");
        Path target=root.resolve(name).normalize();
        if (!target.startsWith(root) || Files.isSymbolicLink(target)) throw new IllegalArgumentException("Invalid stored path");
        return target;
    }

	/**
	 * 파일 크기 검증
	 */
	public boolean isValidFileSize(MultipartFile file, long maxSizeInBytes) {
		return file.getSize() <= maxSizeInBytes;
	}

	/**
	 * PDF 파일 확장자 검증
	 */
	public boolean isPdfFile(MultipartFile file) {
		String originalFileName = file.getOriginalFilename();
		if (originalFileName == null) {
			return false;
		}
		return originalFileName.toLowerCase().endsWith(".pdf");
	}
}