import numpy as np
from transformers import AutoTokenizer
import onnxruntime as ort
from bs4 import BeautifulSoup, MarkupResemblesLocatorWarning
import warnings
warnings.filterwarnings("ignore", category=MarkupResemblesLocatorWarning, module='bs4')

class MlTagging:
    """
    This class will be used for automatically tagging Articles
    @Authors: Marcel Franzen, 2023
              Alexander Ohlei, 2023
    """
    
    tokenizer = AutoTokenizer.from_pretrained(
        "Tobias/bert-base-german-cased_German_Hotel_classification"
    )

    model_categories_first_ressort = ort.InferenceSession("/home/molonews/molonews/ml/models/1_categories_model.onnx")

    model_categories_second_third_ressort = ort.InferenceSession(
        "/home/molonews/molonews/ml/models/2-3_categories_model.onnx"
    )   
    categories_first_ressort = [
        "Fußball",
        "andere Sportarten",
        "Kultur",
        "Politik",
        "Wohnen",
        "Umwelt",
        "Wissenschaft",
        "Bildung",
        "Wirtschaft",
        "Gemeinschaft",
        "Kriminalität",
        "Unglück",
        "Corona",
        "Gesundheit",
    ]
    categories_second_third_ressort = [
        "Werdegang",
        "Kulturelles Engagement",
        "Soziales Engagement",
        "Nachhaltigkeit",
        "Politisches Engagement",
        "Fahrrad & E-Scooter",
        "Auto",
        "Motorrad",
        "Fußgänger",
        "Öffis",
        "Baustellen",
        "Stau",
    ]

    def predict_categories(self, model, categories, num_categories, input_ids, attention_mask):
        """
        This method takes care of the prediction of the the tags
        :param model: the ml model
        :param categories: the categories that will be predicted
        :param num_categories: the amount of categories that will be predicted
        :param input ids: ???
        :param attention_mask: ==
        return: predicted tags
        """
        outputs = model.run(
            None,
            {
                "input_ids": input_ids.astype(np.int32),
                "attention_mask": attention_mask.astype(np.int32),
            },
        )
        outputs = np.asarray(outputs[0][0])

        idxs = np.flip(np.argsort(outputs))[:num_categories]

        res_pred = []
        for j in idxs:
            res_pred.append(categories[j])

        return res_pred
    

    def tag_news_article(self, title, abstract):
        """
        This method creates the tags for a provided article title and abstract 
        based on the ml model inside the class
        :param title: the title of the article
        :param abstract: the abstract of the article
        :return: a list of tags (currently exactly four)
        """
        # remove html tags from abstract
        soup = BeautifulSoup(abstract, features="html.parser")
        clean_abstract = soup.get_text()

        tokenized_inputs = self.tokenizer(
            str(title) + str(clean_abstract),
            return_tensors="np",
            padding="max_length",
            truncation=True,
            max_length=60,
            add_special_tokens=True,
        )

        input_ids = np.expand_dims(tokenized_inputs["input_ids"][0], axis=0)

        attention_mask = np.expand_dims(tokenized_inputs["attention_mask"][0], axis=0)

        first = self.predict_categories(self.model_categories_first_ressort,self.categories_first_ressort,2,input_ids, attention_mask)

        second = self.predict_categories(self.model_categories_second_third_ressort,self.categories_second_third_ressort,1,input_ids,attention_mask)
        
        # Corona aus der Liste löschen

        if "Corona" in first: first.remove("Corona")

        return first + second
  
    def __init__(self):
        pass

