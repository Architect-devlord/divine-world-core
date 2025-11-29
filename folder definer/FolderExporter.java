import java.io.*;
import java.text.SimpleDateFormat;
import java.util.Date;

public class FolderExporter {
    // ANSI colors
    private static final String RESET = "\u001B[0m";
    private static final String BLUE = "\u001B[34m";
    private static final String GREEN = "\u001B[32m";
    private static final String YELLOW = "\u001B[33m";
    private static final String CYAN = "\u001B[36m";
    private static final String RED = "\u001B[31m";
    private static final String MAGENTA = "\u001B[35m";
    private static final String BOLD = "\u001B[1m";

    private static boolean includeContents = false;
    private static boolean stepByStep = false;
    private static boolean autoContinue = false;

    private static BufferedReader reader = new BufferedReader(new InputStreamReader(System.in));

    private static int totalFiles = 0;
    private static int processedFiles = 0;

    public static void main(String[] args) {
        try {
            System.out.print(CYAN + "📂 Drag and drop the folder here: " + RESET);
            String input = reader.readLine();

            input = input.replace("\"", "").trim();
            File folder = new File(input).getAbsoluteFile();

            if (!folder.exists() || !folder.isDirectory()) {
                System.out.println(RED + "❌ Invalid folder path: " + input + RESET);
                return;
            }

            // Preferences
            System.out.print(YELLOW + "📝 Include file contents too? (y/n): " + RESET);
            includeContents = reader.readLine().trim().equalsIgnoreCase("y");

            System.out.print(YELLOW + "⚙️ Dump all at once or step-by-step? (a/s): " + RESET);
            stepByStep = reader.readLine().trim().equalsIgnoreCase("s");

            // Count total files for progress bar
            totalFiles = countFiles(folder);
            System.out.println(CYAN + "📊 Total files to process: " + totalFiles + RESET);

            // Output file
            String timestamp = new SimpleDateFormat("yyyy_MM_dd_HH_mm_ss").format(new Date());
            String desktopPath = System.getProperty("user.home") + File.separator + "Desktop";
            File outputFile = new File(desktopPath, folder.getName() + "-" + timestamp + ".txt");

            PrintWriter writer = new PrintWriter(new FileWriter(outputFile));
            writer.println("📁 Folder Structure Export");
            writer.println("------------------------------------------------------");

            writeFolder(folder, writer, 0);

            writer.close();
            System.out.println(GREEN + "\n✅ Done! Output written to " + outputFile.getAbsolutePath() + RESET);

        } catch (Exception e) {
            e.printStackTrace();
        }
    }

    // Count total files for progress tracking
    private static int countFiles(File folder) {
        int count = 0;
        File[] files = folder.listFiles();
        if (files == null) return 0;
        for (File f : files) {
            if (f.isDirectory()) count += countFiles(f);
            else count++;
        }
        return count;
    }

    private static void writeFolder(File folder, PrintWriter writer, int depth) throws IOException {
        String indent = "  ".repeat(depth);
        writer.println(indent + "📁 " + folder.getName() + "/");

        File[] files = folder.listFiles();
        if (files == null) return;

        for (int i = 0; i < files.length; i++) {
            File f = files[i];
            if (f.isDirectory()) {
                System.out.println(BLUE + "📂 Folder: " + f.getName() + RESET);
                writeFolder(f, writer, depth + 1);
            } else {
                processedFiles++;
                printProgressBar(processedFiles, totalFiles);

                System.out.println(GREEN + "📄 File: " + f.getName() + RESET);
                writer.println(indent + "  📄 " + f.getName());

                if (includeContents) {
                    writer.println(indent + "      --- File Contents ---");
                    try (BufferedReader br = new BufferedReader(new FileReader(f))) {
                        String line;
                        while ((line = br.readLine()) != null) {
                            writer.println(indent + "      " + line);
                        }
                    } catch (Exception ex) {
                        writer.println(indent + "      [Could not read file: " + ex.getMessage() + "]");
                    }
                    writer.println(indent + "      ----------------------");
                }

                if (stepByStep && !autoContinue) {
                    handleStepInteraction(writer, files, i, indent);
                }
            }
        }
    }

    // Step-by-step menu
    private static void handleStepInteraction(PrintWriter writer, File[] files, int currentIndex, String indent) throws IOException {
        System.out.println(GREEN + "\n✅ Wrote: " + files[currentIndex].getName() + RESET);
        if (currentIndex + 1 < files.length) {
            System.out.println(CYAN + "➡️ Next file: " + files[currentIndex + 1].getName() + RESET);
        } else {
            System.out.println(GREEN + "✅ Last file in this folder!" + RESET);
            return;
        }

        System.out.println(MAGENTA + """
            What next?
            [1] Skip next file
            [2] Write remaining without stopping
            [3] Continue step-by-step
            [4] Exit
            """ + RESET);

        System.out.print(YELLOW + "👉 Your choice: " + RESET);
        String choice = reader.readLine().trim();

        switch (choice) {
            case "1" -> {
                writer.println(indent + "  ⚠️ Skipped: " + files[currentIndex + 1].getName());
                System.out.println(YELLOW + "⏭️ Skipping " + files[currentIndex + 1].getName() + RESET);
                if (currentIndex + 2 < files.length) {
                    System.out.println(CYAN + "➡️ Next file after skip: " + files[currentIndex + 2].getName() + RESET);
                }
            }
            case "2" -> {
                System.out.println(GREEN + "🚀 Continuing automatically till end..." + RESET);
                autoContinue = true;
            }
            case "3" -> System.out.println(CYAN + "🔁 Continuing step-by-step..." + RESET);
            case "4" -> {
                System.out.println(RED + "👋 Exiting early." + RESET);
                System.exit(0);
            }
            default -> System.out.println(RED + "⚠️ Invalid input — continuing step-by-step by default." + RESET);
        }
    }

    // Progress bar display
    private static void printProgressBar(int current, int total) {
        int width = 30; // bar length
        double progress = (double) current / total;
        int filled = (int) (progress * width);

        StringBuilder bar = new StringBuilder();
        bar.append(BOLD).append("[");
        for (int i = 0; i < width; i++) {
            bar.append(i < filled ? "#" : "-");
        }
        bar.append("]").append(RESET);

        int percent = (int) (progress * 100);
        System.out.print("\r" + CYAN + "Progress: " + bar + " " + percent + "% (" + current + "/" + total + ")" + RESET);

        if (current == total) System.out.println();
    }
}
