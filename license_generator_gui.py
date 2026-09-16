import tkinter as tk
from tkinter import ttk, messagebox
import datetime
from license_manager import generate_short_license

class LicenseGeneratorApp:
    def __init__(self, root):
        self.root = root
        self.root.title("StarGate License Generator 🔑")
        self.root.geometry("500x350")
        self.root.resizable(False, False)
        
        # Style
        style = ttk.Style()
        style.theme_use('clam')
        
        # Main Frame
        main_frame = ttk.Frame(root, padding="20")
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # Title
        ttk.Label(main_frame, text="أداة توليد رخص وبرمجيات Stargate", font=("Arial", 14, "bold")).pack(pady=(0, 15))
        
        # Input Frame
        input_frame = ttk.Frame(main_frame)
        input_frame.pack(fill=tk.X, pady=5)
        
        # Hardware ID
        ttk.Label(input_frame, text="رقم جهاز المشترك (Hardware GUID):", font=("Arial", 10)).grid(row=0, column=1, sticky=tk.E, pady=5, padx=5)
        self.guid_var = tk.StringVar(value="UNIVERSAL")
        ttk.Entry(input_frame, textvariable=self.guid_var, width=40).grid(row=0, column=0, pady=5)
        ttk.Label(input_frame, text="* اتركه UNIVERSAL ليعمل على أي جهاز", font=("Arial", 8)).grid(row=1, column=0, sticky=tk.E)

        # Duration
        ttk.Label(input_frame, text="مدة الاشتراك (بالأيام):", font=("Arial", 10)).grid(row=2, column=1, sticky=tk.E, pady=15, padx=5)
        self.days_var = tk.StringVar(value="30")
        days_combo = ttk.Combobox(input_frame, textvariable=self.days_var, values=["7", "14", "30", "90", "180", "365", "3650"], width=37)
        days_combo.grid(row=2, column=0, pady=15)
        
        # Generate Button
        ttk.Button(main_frame, text="توليد كود التفعيل 🚀", command=self.generate).pack(pady=15, fill=tk.X)
        
        # Output
        self.output_text = tk.Text(main_frame, height=4, width=50, font=("Consolas", 12))
        self.output_text.pack(fill=tk.X)
        
    def generate(self):
        guid = self.guid_var.get().strip()
        days_str = self.days_var.get().strip()
        
        if not days_str.isdigit():
            messagebox.showerror("خطأ", "يرجى إدخال عدد أيام صحيح")
            return
            
        days = int(days_str)
        try:
            from license_manager import generate_short_license
            code = generate_short_license(guid, days)
            self.output_text.delete(1.0, tk.END)
            self.output_text.insert(tk.END, code)
            
            # Copy to clipboard
            self.root.clipboard_clear()
            self.root.clipboard_append(code)
            
            messagebox.showinfo("تم بنجاح", "تم توليد الكود ونسخه إلى الحافظة بنجاح!")
        except Exception as e:
            messagebox.showerror("خطأ", str(e))

if __name__ == "__main__":
    root = tk.Tk()
    app = LicenseGeneratorApp(root)
    root.mainloop()
