import java.io.BufferedReader;
import java.io.File;
import java.io.FileReader;
import java.io.FileWriter;
import java.io.IOException;
import java.io.InputStreamReader;
import java.io.PrintWriter;
import java.util.HashSet;
import java.util.Set;


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

    private static final Set<String> skipNames = new HashSet<>();

    private static final BufferedReader reader = new BufferedReader(new InputStreamReader(System.in));

    private static int totalFiles = 0;
    private static int processedFiles = 0;

    // Detect OS through menu
    private static String selectedOS = "";

    public static void main(String[] args) {
        try {
            selectOS();

            System.out.print(CYAN + "📂 Drag and drop the folder here or type the absolute folder path: " + RESET);
            String input = reader.readLine();

            input = cleanPath(input);

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

            // Count total files
            totalFiles = countFiles(folder);
            System.out.println(CYAN + "📊 Total files to process: " + totalFiles + RESET);

            // Ask the user where to store the result
            System.out.print(CYAN + "📁 Enter path to save the output file: " + RESET);
            String outputPath = cleanPath(reader.readLine());

            File directory = new File(outputPath);
            if (!directory.exists() || !directory.isDirectory()) {
                System.out.println(RED + "❌ Invalid directory: " + outputPath + RESET);
                return;
            }

            // Generate file without timestamp
            File outputFile = new File(directory, folder.getName() + ".txt");

            try (PrintWriter writer = new PrintWriter(new FileWriter(outputFile))) {
                writer.println("📁 Folder Structure Export");
                writer.println("------------------------------------------------------");
                
                writeFolder(folder, writer, 0);
            }
            System.out.println(GREEN + "\n✅ Done! Output written to " + outputFile.getAbsolutePath() + RESET);

        } catch (IOException e) {
            e.printStackTrace();
        }
    }

    // OS Selection
    private static void selectOS() throws IOException {
        System.out.println(MAGENTA + """
                Select your operating system:
                [1] Windows
                [2] Linux (Arch, Ubuntu, etc.)
                """ + RESET);

        System.out.print(YELLOW + "👉 Your choice: " + RESET);
        String choice = reader.readLine().trim();

        switch (choice) {
            case "1" -> {
                selectedOS = "windows";
                System.out.println(GREEN + "✔ Windows selected." + RESET);
            }
            case "2" -> {
                selectedOS = "linux";
                System.out.println(GREEN + "✔ Linux selected." + RESET);
            }
            default -> {
                System.out.println(RED + "Invalid. Defaulting to Linux." + RESET);
                selectedOS = "linux";
            }
        }
    }

    // OS-aware cleanup
    private static String cleanPath(String path) {
        path = path.trim();

        // Remove quotes around drag-and-drop paths
        path = path.replace("\"", "");

        if (selectedOS.equals("linux")) {
            return path.replace("\\ ", " "); // Clean escaped spaces
        }

        return path;
    }

    // Count total files
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
            // Skip by name
        if (skipNames.contains(f.getName()) || skipNames.contains(folder.getName())) {
            writer.println(indent + "  ⚠️ Skipped by name: " + f.getName());
            System.out.println(YELLOW + "⏭️ Skipped (name match): " + f.getName() + RESET);
            continue;
        }

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

    // Step-by-step interaction
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
            [4] Add skip-by-name rules
            [5] Exit
            """ + RESET);


        System.out.print(YELLOW + "👉 Your choice: " + RESET);
        String choice = reader.readLine().trim();

        switch (choice) {
            case "1" -> {
                writer.println(indent + "  ⚠️ Skipped: " + files[currentIndex + 1].getName());
                System.out.println(YELLOW + "⏭️ Skipping " + files[currentIndex + 1].getName() + RESET);
            }
            case "2" -> {
                System.out.println(GREEN + "🚀 Continuing automatically till end..." + RESET);
                autoContinue = true;
            }
            case "3" -> System.out.println(CYAN + "🔁 Continuing step-by-step..." + RESET);
            case "4" -> {
                collectSkipNames();  // <-- NEW FEATURE
                System.out.println(GREEN + "✔ Skip rules added." + RESET);
                }
            case "5" -> {
                System.out.println(RED + "👋 Exiting early." + RESET);
                System.exit(0);
                }
            default -> System.out.println(RED + "⚠️ Invalid input — continuing step-by-step by default." + RESET);
        }
    }

    // Clean and stable progress bar (cross-platform)
    private static void printProgressBar(int current, int total) {
        int width = 40;

        double progress = (double) current / total;
        int filled = (int) (progress * width);
        int percent = (int) (progress * 100);

        String bar = "[" +
                "#".repeat(filled) +
                "-".repeat(width - filled) +
                "]";

        String output = String.format(
                "\r%sProgress:%s %s %3d%% (%d/%d)%s",
                CYAN, RESET, bar, percent, current, total, RESET
        );

        System.out.print(output);

        if (current == total) {
            System.out.println(); // move to next line at finish
        }
    }   

    // Collect skip names from user
    private static void collectSkipNames() throws IOException {
    while (true) {
        System.out.print(YELLOW + "Enter file/folder name to skip: " + RESET);
        String name = reader.readLine().trim();

        if (!name.isEmpty()) {
            skipNames.add(name);
            System.out.println(GREEN + "✔ Added to skip list: " + name + RESET);
        }

        System.out.print(YELLOW + "Add more? (y/n): " + RESET);
        String more = reader.readLine().trim().toLowerCase();

        if (!more.equals("y")) {
            System.out.println(CYAN + "Skip list: " + skipNames + RESET);
            break;
        }
    }
}
}